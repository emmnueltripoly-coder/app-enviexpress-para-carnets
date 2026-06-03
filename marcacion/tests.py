"""
Tests del Hito 3 (Núcleo de marcación) — corren contra PostgreSQL real.

Verifican:
  (a) Marcación válida dentro de la geocerca -> fuera_de_sede=False.
  (b) Marcación con token QR vencido -> 400.
  (c) Marcación con coordenadas lejanas -> fuera_de_sede=True y distancia > radio.
  (d) Doble marcación idéntica -> rechazada (constraint / verificación).
  (e) Corrección -> NUEVO registro con corrige_a, sin alterar el original.
  (f) Concurrencia -> dos peticiones simultáneas no crean dos registros.
  (g) AUDITOR -> 403 al intentar marcar.
Extra: Haversine de referencia, inmutabilidad por trigger, empleado no genera QR.
"""

import threading
import time
from datetime import date
from decimal import Decimal
from unittest import mock

import pytest
from django.db import IntegrityError, connection, transaction
from rest_framework.test import APIClient

from auditoria.models import AuditLog
from marcacion.models import Marcacion
from marcacion.services import (
    MarcacionDuplicada,
    generar_token_qr,
    haversine_metros,
    registrar_marcacion,
)
from organizacion.models import Empresa, Sede
from personal.models import Empleado, Usuario

# Centro de la sede (Medellín) usado en los tests.
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


def _crear_empleado(sede, *, username="cc.empleado", documento="1001", rol=Usuario.Rol.EMPLEADO):
    usuario = Usuario.objects.create_user(
        username=username, password="ClaveSegura123", rol=rol
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


# --------------------------------------------------------------------------
# (a) Dentro de la geocerca
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_marcacion_dentro_de_geocerca():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    resp = client.post(
        "/api/marcacion/",
        {
            "token_qr": generar_token_qr(sede.pk),
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        format="json",
    )

    assert resp.status_code == 201, resp.data
    assert resp.data["fuera_de_sede"] is False
    assert Decimal(resp.data["distancia_metros"]) < Decimal("1")
    # Quedó auditada.
    assert AuditLog.objects.filter(accion=AuditLog.Accion.MARCACION).count() == 1


# --------------------------------------------------------------------------
# (b) Token vencido
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_marcacion_token_vencido_rechazada():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    # Token firmado "hace 100 s" -> excede los 45 s de vigencia.
    with mock.patch("time.time", return_value=time.time() - 100):
        token_viejo = generar_token_qr(sede.pk)

    resp = client.post(
        "/api/marcacion/",
        {
            "token_qr": token_viejo,
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        format="json",
    )

    assert resp.status_code == 400
    assert "venc" in resp.data["detail"].lower()
    assert Marcacion.objects.count() == 0


# --------------------------------------------------------------------------
# (c) Fuera de la geocerca
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_marcacion_fuera_de_geocerca():
    sede = _crear_sede(radio=100)
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    # Punto a varios km del centro de la sede.
    resp = client.post(
        "/api/marcacion/",
        {
            "token_qr": generar_token_qr(sede.pk),
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": "6.300000",
            "longitud": "-75.600000",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.data
    assert resp.data["fuera_de_sede"] is True
    distancia = Decimal(resp.data["distancia_metros"])
    assert distancia > sede.radio_metros
    assert Decimal("5000") < distancia < Decimal("8000")  # rango esperado ~6.5 km


# --------------------------------------------------------------------------
# (d) Doble marcación idéntica
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_doble_marcacion_rechazada():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)
    token = generar_token_qr(sede.pk)

    payload = {
        "token_qr": token,
        "tipo": Marcacion.Tipo.ENTRADA,
        "latitud": str(SEDE_LAT),
        "longitud": str(SEDE_LON),
    }
    r1 = client.post("/api/marcacion/", payload, format="json")
    r2 = client.post("/api/marcacion/", payload, format="json")

    assert r1.status_code == 201
    assert r2.status_code == 409  # rechazada
    assert Marcacion.objects.count() == 1


@pytest.mark.django_db
def test_doble_marcacion_a_nivel_bd_constraint():
    """El índice único parcial bloquea el INSERT duplicado aunque se evada el servicio."""
    sede = _crear_sede()
    empleado = _crear_empleado(sede)

    comun = dict(
        empleado=empleado,
        sede=sede,
        latitud=SEDE_LAT,
        longitud=SEDE_LON,
        fuera_de_sede=False,
        distancia_metros=Decimal("0.00"),
        tipo=Marcacion.Tipo.ENTRADA,
    )
    m1 = Marcacion.objects.create(**comun)
    # Misma marca, mismo minuto -> viola el índice único parcial.
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Marcacion.objects.create(minuto_marcacion=m1.minuto_marcacion, **comun)


# --------------------------------------------------------------------------
# (e) Corrección
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_correccion_crea_registro_nuevo_sin_alterar_original():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    rrhh = Usuario.objects.create_user(
        username="rrhh1", password="ClaveSegura123", rol=Usuario.Rol.RRHH
    )

    original = registrar_marcacion(
        empleado=empleado,
        token_qr=generar_token_qr(sede.pk),
        tipo=Marcacion.Tipo.ENTRADA,
        latitud=SEDE_LAT,
        longitud=SEDE_LON,
    )
    tipo_original = original.tipo

    client = APIClient()
    client.force_authenticate(user=rrhh)
    resp = client.post(
        f"/api/marcacion/{original.pk}/corregir/",
        {
            "tipo": Marcacion.Tipo.SALIDA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
            "motivo": "El empleado marcó tipo equivocado.",
        },
        format="json",
    )

    assert resp.status_code == 201, resp.data
    assert str(resp.data["corrige_a"]) == str(original.pk)
    assert resp.data["tipo"] == Marcacion.Tipo.SALIDA

    # El original NO cambió y sigue existiendo.
    original.refresh_from_db()
    assert original.tipo == tipo_original
    assert original.corrige_a_id is None
    assert Marcacion.objects.count() == 2


# --------------------------------------------------------------------------
# (f) Concurrencia
# --------------------------------------------------------------------------
@pytest.mark.django_db(transaction=True)
def test_concurrencia_no_crea_doble():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    token = generar_token_qr(sede.pk)

    barrera = threading.Barrier(2)
    resultados = []

    def intentar():
        barrera.wait()  # ambos hilos arrancan a la vez
        try:
            registrar_marcacion(
                empleado=empleado,
                token_qr=token,
                tipo=Marcacion.Tipo.ENTRADA,
                latitud=SEDE_LAT,
                longitud=SEDE_LON,
            )
            resultados.append("ok")
        except (MarcacionDuplicada, IntegrityError):
            resultados.append("dup")
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
        assert sorted(resultados) == ["dup", "ok"]
    finally:
        # transaction=True commitea los datos; pytest-django trunca en teardown,
        # pero limpiamos explícitamente (TRUNCATE no dispara el trigger de
        # inmutabilidad, que solo cubre UPDATE/DELETE por fila).
        with connection.cursor() as c:
            c.execute("TRUNCATE marcacion, audit_log CASCADE;")


# --------------------------------------------------------------------------
# (g) AUDITOR no puede marcar
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_auditor_no_puede_marcar():
    sede = _crear_sede()
    auditor = Usuario.objects.create_user(
        username="auditor1", password="ClaveSegura123", rol=Usuario.Rol.AUDITOR
    )
    client = APIClient()
    client.force_authenticate(user=auditor)

    resp = client.post(
        "/api/marcacion/",
        {
            "token_qr": generar_token_qr(sede.pk),
            "tipo": Marcacion.Tipo.ENTRADA,
            "latitud": str(SEDE_LAT),
            "longitud": str(SEDE_LON),
        },
        format="json",
    )
    assert resp.status_code == 403
    assert Marcacion.objects.count() == 0


# --------------------------------------------------------------------------
# Extra: Haversine de referencia, inmutabilidad por trigger, QR restringido
# --------------------------------------------------------------------------
def test_haversine_referencia():
    # 1° de longitud en el ecuador ≈ 111195 m.
    d = haversine_metros(0, 0, 0, 1)
    assert abs(d - 111195) < 2


@pytest.mark.django_db
def test_marcacion_update_directo_rechazado_por_trigger():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    m = registrar_marcacion(
        empleado=empleado,
        token_qr=generar_token_qr(sede.pk),
        tipo=Marcacion.Tipo.ENTRADA,
        latitud=SEDE_LAT,
        longitud=SEDE_LON,
    )
    with pytest.raises(Exception):
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute(
                    "UPDATE marcacion SET tipo='SALIDA' WHERE id=%s", [str(m.pk)]
                )


@pytest.mark.django_db
def test_empleado_no_puede_generar_qr():
    sede = _crear_sede()
    empleado = _crear_empleado(sede)
    client = APIClient()
    client.force_authenticate(user=empleado.usuario)

    resp = client.get(f"/api/marcacion/qr/?sede_id={sede.pk}")
    assert resp.status_code == 403
