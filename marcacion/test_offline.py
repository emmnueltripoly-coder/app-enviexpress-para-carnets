"""
Tests del Hito 4 (Sincronización offline) — corren contra PostgreSQL real.

Verifican:
  (a) Marcación offline con QR válido se sincroniza y su hora oficial =
      timestamp_qr (NO la del dispositivo).
  (b) Reenviar el MISMO token offline no crea una segunda marcación (idempotencia).
  (c) Un lote con varias marcaciones responde el estado de cada una.
  (d) QR muy antiguo (fuera de tolerancia) se acepta pero con revisar_offline=True.
  (e) timestamp_dispositivo grotescamente desfasado levanta la bandera.
  (f) Concurrencia: dos sync simultáneas del mismo token crean UNA marcación.
  (g) El AUDITOR recibe 403 al sincronizar.
"""

import threading
from datetime import date, timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from auditoria.models import AuditLog
from marcacion.models import Marcacion
from marcacion.services import (
    ESTADO_ACEPTADA,
    ESTADO_DUPLICADA,
    ESTADO_REVISAR,
    generar_token_qr,
    sincronizar_item_offline,
)
from organizacion.models import Empresa, Sede
from personal.models import Empleado, Usuario

SEDE_LAT = Decimal("6.244203")
SEDE_LON = Decimal("-75.581215")


def _crear_sede(radio=100):
    empresa = Empresa.objects.create(nombre="Enviexpress", nit="900123456-7")
    return Sede.objects.create(
        empresa=empresa,
        nombre="Sede Medellín",
        ciudad=Sede.Ciudad.MEDELLIN,
        direccion="Calle 10 # 20-30",
        latitud=SEDE_LAT,
        longitud=SEDE_LON,
        radio_metros=radio,
    )


def _crear_empleado(sede, *, username="cc.empleado", documento="1001"):
    usuario = Usuario.objects.create_user(
        username=username, password="ClaveSegura123", rol=Usuario.Rol.EMPLEADO
    )
    return Empleado.objects.create(
        usuario=usuario,
        documento_identidad=documento,
        nombres="Ana",
        apellidos="López",
        sede=sede,
        cargo="Auxiliar",
        fecha_ingreso=date(2026, 1, 15),
    )


def _token_qr(sede, *, generado=None):
    """Genera un token QR; si 'generado' se da, simula esa hora de emisión."""
    if generado is None:
        return generar_token_qr(sede.pk)
    with mock.patch("django.utils.timezone.now", return_value=generado):
        return generar_token_qr(sede.pk)


def _post_sync(client, items):
    return client.post(
        "/api/marcacion/sync/", {"marcaciones": items}, format="json"
    )


# --------------------------------------------------------------------------
# (a) Hora oficial = timestamp_qr, no la del dispositivo
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_hora_oficial_es_timestamp_qr():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    # QR emitido hace 2 horas (el empleado estuvo frente al kiosco entonces).
    hora_qr = (timezone.now() - timedelta(hours=2)).replace(microsecond=0)
    token = _token_qr(sede, generado=hora_qr)
    # El celular reporta una hora distinta (informativa).
    hora_celular = hora_qr + timedelta(minutes=1)

    resp = _post_sync(
        client,
        [
            {
                "token_qr": token,
                "tipo": Marcacion.Tipo.ENTRADA,
                "latitud": str(SEDE_LAT),
                "longitud": str(SEDE_LON),
                "timestamp_dispositivo": hora_celular.isoformat(),
            }
        ],
    )

    assert resp.status_code == 200, resp.data
    item = resp.data["resultados"][0]
    assert item["estado"] == ESTADO_ACEPTADA

    m = Marcacion.objects.get(pk=item["marcacion_id"])
    assert m.es_offline is True
    # La hora OFICIAL es la del QR, no la del dispositivo ni la del envío.
    assert m.timestamp_qr == hora_qr
    assert m.minuto_marcacion == hora_qr.replace(second=0, microsecond=0)
    assert m.timestamp_dispositivo == hora_celular
    assert m.timestamp_servidor > m.timestamp_qr  # el envío llegó después


# --------------------------------------------------------------------------
# (b) Idempotencia / anti-replay
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_reenvio_mismo_token_es_idempotente():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    token = _token_qr(sede)
    item = {
        "token_qr": token,
        "tipo": Marcacion.Tipo.ENTRADA,
        "latitud": str(SEDE_LAT),
        "longitud": str(SEDE_LON),
    }

    r1 = _post_sync(client, [item])
    r2 = _post_sync(client, [item])  # reenvío del MISMO token

    assert r1.data["resultados"][0]["estado"] == ESTADO_ACEPTADA
    assert r2.data["resultados"][0]["estado"] == ESTADO_DUPLICADA
    # Misma marcación devuelta ambas veces; solo existe UNA.
    assert r1.data["resultados"][0]["marcacion_id"] == r2.data["resultados"][0]["marcacion_id"]
    assert Marcacion.objects.count() == 1


# --------------------------------------------------------------------------
# (c) Lote con varias marcaciones
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_lote_responde_estado_por_item():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    token_ok = _token_qr(sede)
    items = [
        {  # 0: aceptada (entrada)
            "token_qr": token_ok,
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        {  # 1: replay del mismo token -> duplicada
            "token_qr": token_ok,
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        {  # 2: token basura -> rechazada
            "token_qr": "firma-invalida.xxx.yyy",
            "tipo": Marcacion.Tipo.SALIDA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        {  # 3: otra salida con QR nuevo válido -> aceptada
            "token_qr": _token_qr(sede),
            "tipo": Marcacion.Tipo.SALIDA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
    ]

    resp = _post_sync(client, items)
    assert resp.status_code == 200, resp.data
    estados = [r["estado"] for r in resp.data["resultados"]]
    assert estados == [
        ESTADO_ACEPTADA,
        ESTADO_DUPLICADA,
        "RECHAZADA",
        ESTADO_ACEPTADA,
    ]
    # Solo se crearon las 2 aceptadas.
    assert Marcacion.objects.count() == 2


# --------------------------------------------------------------------------
# (d) QR muy antiguo -> aceptado pero con bandera
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_qr_antiguo_levanta_bandera():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    # QR emitido hace 3 días (fuera de la tolerancia de 24 h).
    hora_qr = (timezone.now() - timedelta(days=3)).replace(microsecond=0)
    token = _token_qr(sede, generado=hora_qr)

    resp = _post_sync(
        client,
        [
            {
                "token_qr": token,
                "tipo": Marcacion.Tipo.ENTRADA,
                "latitud": str(SEDE_LAT),
                "longitud": str(SEDE_LON),
            }
        ],
    )

    item = resp.data["resultados"][0]
    assert item["estado"] == ESTADO_REVISAR
    assert item["revisar_offline"] is True
    assert "QR_ANTIGUO" in item["motivos"]

    m = Marcacion.objects.get(pk=item["marcacion_id"])
    assert m.revisar_offline is True  # aceptada, NO bloqueada
    assert m.timestamp_qr == hora_qr


# --------------------------------------------------------------------------
# (e) Desfase grosero del dispositivo -> bandera
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_desfase_dispositivo_levanta_bandera():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    hora_qr = timezone.now().replace(microsecond=0)
    token = _token_qr(sede, generado=hora_qr)
    # Celular desfasado 5 horas respecto a la hora oficial.
    hora_celular = hora_qr - timedelta(hours=5)

    resp = _post_sync(
        client,
        [
            {
                "token_qr": token,
                "tipo": Marcacion.Tipo.ENTRADA,
                "latitud": str(SEDE_LAT),
                "longitud": str(SEDE_LON),
                "timestamp_dispositivo": hora_celular.isoformat(),
            }
        ],
    )

    item = resp.data["resultados"][0]
    assert item["estado"] == ESTADO_REVISAR
    assert "DESFASE_DISPOSITIVO" in item["motivos"]
    m = Marcacion.objects.get(pk=item["marcacion_id"])
    assert m.revisar_offline is True


# --------------------------------------------------------------------------
# (f) Concurrencia: dos sync del mismo token -> una marcación
# --------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_offline_concurrencia_mismo_token_una_marcacion():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    token = _token_qr(sede)

    barrera = threading.Barrier(2)
    estados = []

    def intentar():
        barrera.wait()
        try:
            res = sincronizar_item_offline(
                empleado=empleado,
                token_qr=token,
                tipo=Marcacion.Tipo.ENTRADA,
                latitud=SEDE_LAT,
                longitud=SEDE_LON,
            )
            estados.append(res["estado"])
        finally:
            connection.close()

    h1 = threading.Thread(target=intentar)
    h2 = threading.Thread(target=intentar)
    h1.start()
    h2.start()
    h1.join()
    h2.join()

    try:
        assert Marcacion.objects.count() == 1
        assert sorted(estados) == [ESTADO_ACEPTADA, ESTADO_DUPLICADA]
    finally:
        with connection.cursor() as c:
            c.execute("TRUNCATE marcacion, audit_log CASCADE;")


# --------------------------------------------------------------------------
# (g) Auditor 403
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_auditor_recibe_403():
    sede = _crear_sede()
    auditor = Usuario.objects.create_user(
        username="auditor1", password="ClaveSegura123", rol=Usuario.Rol.AUDITOR
    )
    client = APIClient()
    client.force_authenticate(user=auditor)

    resp = _post_sync(
        client,
        [
            {
                "token_qr": _token_qr(sede),
                "tipo": Marcacion.Tipo.ENTRADA,
                "latitud": str(SEDE_LAT),
                "longitud": str(SEDE_LON),
            }
        ],
    )
    assert resp.status_code == 403
    assert Marcacion.objects.count() == 0


# --------------------------------------------------------------------------
# Extra: el replay queda registrado en auditoría para RRHH
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_offline_replay_queda_en_auditoria():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    token = _token_qr(sede)

    sincronizar_item_offline(
        empleado=empleado, token_qr=token, tipo=Marcacion.Tipo.ENTRADA,
        latitud=SEDE_LAT, longitud=SEDE_LON,
    )
    sincronizar_item_offline(
        empleado=empleado, token_qr=token, tipo=Marcacion.Tipo.ENTRADA,
        latitud=SEDE_LAT, longitud=SEDE_LON,
    )

    replays = [
        log for log in AuditLog.objects.filter(accion=AuditLog.Accion.MARCACION)
        if log.metadata.get("replay") is True
    ]
    assert len(replays) == 1
