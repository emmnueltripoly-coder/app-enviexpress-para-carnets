"""
Servicios de marcación (Hito 3).

Contiene:
- Haversine: distancia en metros entre dos coordenadas.
- QR del kiosco: token FIRMADO con SECRET_KEY (django.core.signing) que codifica
  la sede y expira en 45 s. No requiere dependencias extra y la firma evita la
  falsificación del QR (mitigación de fraude).
- registrar_marcacion(): valida token, calcula geocerca (flexible), e inserta la
  marcación de forma segura ante concurrencia (select_for_update + constraint de
  exclusión). Audita vía AuditService (único punto del Hito 0).
- corregir_marcacion(): crea una NUEVA marcación con corrige_a (nunca edita).
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from auditoria.models import AuditLog
from auditoria.services import AuditService
from organizacion.models import Sede
from personal.models import Empleado

from .models import Marcacion

# Vigencia del QR del kiosco (segundos) y sal de firma.
QR_MAX_AGE_SEGUNDOS = 45
QR_SALT = "kiosco-qr-marcacion-v1"

# Ventana (segundos) para la verificación amigable de doble-marcación previa al
# INSERT. La garantía dura la da el índice único parcial de la BD.
VENTANA_ANTIDUPLICADO_SEGUNDOS = 60

# Tolerancias OFFLINE (banderas de revisión RRHH, NO bloqueo):
# - Antigüedad: si el QR oficial es más viejo que esto al sincronizar, se marca.
TOLERANCIA_ANTIGUEDAD = timedelta(hours=24)
# - Desfase del dispositivo: si la hora del celular se aparta de la hora oficial
#   más que esto, se marca (la hora del celular es solo informativa).
TOLERANCIA_DESFASE_DISPOSITIVO = timedelta(minutes=15)

RADIO_TIERRA_METROS = 6_371_000

# Estados posibles de cada ítem de un lote de sincronización offline.
ESTADO_ACEPTADA = "ACEPTADA"
ESTADO_REVISAR = "REVISAR"
ESTADO_DUPLICADA = "DUPLICADA"
ESTADO_RECHAZADA = "RECHAZADA"


# --------------------------------------------------------------------------
# Excepciones de dominio (las traduce la capa de vistas a códigos HTTP).
# --------------------------------------------------------------------------
class TokenQRVencido(Exception):
    """El token del QR superó su vigencia (45 s)."""


class TokenQRInvalido(Exception):
    """El token del QR está mal formado o su firma no es válida."""


class MarcacionDuplicada(Exception):
    """Ya existe una marcación equivalente dentro de la ventana de tolerancia."""


# --------------------------------------------------------------------------
# Geocerca
# --------------------------------------------------------------------------
def haversine_metros(lat1, lon1, lat2, lon2) -> float:
    """Distancia en metros entre dos puntos (fórmula de Haversine)."""
    lat1, lon1, lat2, lon2 = map(float, (lat1, lon1, lat2, lon2))
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = (
        sin(dlat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    )
    return 2 * RADIO_TIERRA_METROS * asin(sqrt(a))


def _a_decimal_metros(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------
# QR firmado del kiosco
# --------------------------------------------------------------------------
# El payload del QR incluye:
#   - sede_id: sede a la que pertenece el kiosco.
#   - jti: identificador único del token (anti-replay/idempotencia).
#   - ts: HORA OFICIAL del servidor al emitir el QR (ISO 8601, UTC). Es la hora
#     confiable que cuenta para la asistencia, también en sincronización offline.
def generar_token_qr(sede_id: int) -> str:
    """Devuelve un token firmado (SECRET_KEY) que codifica sede + jti + hora."""
    payload = {
        "sede_id": sede_id,
        "jti": uuid.uuid4().hex,
        "ts": timezone.now().isoformat(),
    }
    return signing.dumps(payload, salt=QR_SALT, compress=True)


def _cargar_payload(token: str, *, max_age) -> dict:
    """Verifica la firma del token y devuelve el payload.

    Si ``max_age`` es None, NO se valida la antigüedad (caso offline: la firma
    debe seguir siendo válida aunque el dato llegue horas después).
    """
    try:
        return signing.loads(token, salt=QR_SALT, max_age=max_age)
    except signing.SignatureExpired:
        raise TokenQRVencido(
            "El código QR venció. Solicite uno nuevo en el kiosco."
        )
    except signing.BadSignature:
        raise TokenQRInvalido("El código QR no es válido.")


def validar_token_qr(token: str) -> dict:
    """Marcación ONLINE: valida firma + vigencia (45 s). Devuelve el payload."""
    return _cargar_payload(token, max_age=QR_MAX_AGE_SEGUNDOS)


def validar_token_qr_offline(token: str) -> dict:
    """Sincronización OFFLINE: valida SOLO la firma (sin vigencia). Payload."""
    return _cargar_payload(token, max_age=None)


def _hora_oficial_desde_payload(payload: dict):
    """Extrae la hora oficial (timestamp_qr) del payload del QR."""
    ts = payload.get("ts")
    return parse_datetime(ts) if ts else None


# --------------------------------------------------------------------------
# Registro de marcación
# --------------------------------------------------------------------------
def _construir_geocerca(sede: Sede, latitud, longitud):
    distancia = haversine_metros(latitud, longitud, sede.latitud, sede.longitud)
    fuera = distancia > float(sede.radio_metros)
    return _a_decimal_metros(distancia), fuera


@transaction.atomic
def registrar_marcacion(
    *,
    empleado: Empleado,
    token_qr: str,
    tipo: str,
    latitud,
    longitud,
    ip_origen: Optional[str] = None,
) -> Marcacion:
    """Valida QR + geocerca y crea la marcación de forma concurrencia-segura.

    Orden: (a) token vigente y firmado; (b) cálculo de distancia/geocerca;
    (c) inserción atómica anti-duplicado (lock + constraint).
    """
    # (a) Token (online: firma + vigencia 45 s)
    payload = validar_token_qr(token_qr)
    sede = Sede.objects.get(pk=payload["sede_id"])
    qr_jti = payload.get("jti")
    timestamp_qr = _hora_oficial_desde_payload(payload)

    # (b) Geocerca flexible (no bloquea; marca para revisión)
    distancia_metros, fuera_de_sede = _construir_geocerca(sede, latitud, longitud)

    # (c) Inserción anti-duplicado.
    # select_for_update serializa las peticiones del MISMO empleado, de modo que
    # ante dos llamadas concurrentes la segunda vea la primera y devuelva un
    # error amigable. El índice único parcial es la garantía dura final.
    Empleado.objects.select_for_update().get(pk=empleado.pk)

    limite = timezone.now() - timedelta(seconds=VENTANA_ANTIDUPLICADO_SEGUNDOS)
    duplicada = Marcacion.objects.filter(
        empleado=empleado,
        tipo=tipo,
        corrige_a__isnull=True,
        timestamp_servidor__gte=limite,
    ).exists()
    if duplicada:
        raise MarcacionDuplicada(
            "Ya se registró una marcación equivalente hace instantes."
        )

    try:
        marcacion = Marcacion.objects.create(
            empleado=empleado,
            sede=sede,
            tipo=tipo,
            latitud=latitud,
            longitud=longitud,
            fuera_de_sede=fuera_de_sede,
            distancia_metros=distancia_metros,
            timestamp_qr=timestamp_qr,
            qr_jti=qr_jti,
        )
    except IntegrityError:
        # Carrera que evadió la verificación previa: la constraint la atrapó.
        raise MarcacionDuplicada(
            "Ya se registró una marcación equivalente hace instantes."
        )

    AuditService.registrar(
        accion=AuditLog.Accion.MARCACION,
        entidad="Marcacion",
        entidad_id=str(marcacion.pk),
        actor_id=str(empleado.usuario_id),
        actor_rol=empleado.usuario.rol,
        ip_origen=ip_origen,
        metadata={
            "tipo": tipo,
            "sede_id": sede.pk,
            "fuera_de_sede": fuera_de_sede,
            "distancia_metros": str(distancia_metros),
            "es_offline": False,
            "qr_jti": qr_jti,
        },
    )
    return marcacion


@transaction.atomic
def corregir_marcacion(
    *,
    original: Marcacion,
    tipo: str,
    latitud,
    longitud,
    actor_id: Optional[str] = None,
    actor_rol: Optional[str] = None,
    ip_origen: Optional[str] = None,
    motivo: str = "",
) -> Marcacion:
    """Crea una NUEVA marcación que corrige a ``original`` (no edita el original).

    La nueva marcación queda exenta de la constraint anti-duplicado por tener
    ``corrige_a`` no nulo. Se audita como MARCACION con metadata de corrección.
    """
    distancia_metros, fuera_de_sede = _construir_geocerca(
        original.sede, latitud, longitud
    )

    correccion = Marcacion.objects.create(
        empleado=original.empleado,
        sede=original.sede,
        tipo=tipo,
        latitud=latitud,
        longitud=longitud,
        fuera_de_sede=fuera_de_sede,
        distancia_metros=distancia_metros,
        corrige_a=original,
    )

    AuditService.registrar(
        accion=AuditLog.Accion.MARCACION,
        entidad="Marcacion",
        entidad_id=str(correccion.pk),
        actor_id=actor_id,
        actor_rol=actor_rol,
        ip_origen=ip_origen,
        metadata={
            "tipo": tipo,
            "correccion": True,
            "corrige_a": str(original.pk),
            "motivo": motivo,
        },
    )
    return correccion


# --------------------------------------------------------------------------
# Sincronización OFFLINE (Hito 4)
# --------------------------------------------------------------------------
# Integridad temporal: la HORA OFICIAL es timestamp_qr (firmada por el servidor
# dentro del QR). El celular (timestamp_dispositivo) es solo informativo. Una
# marcación offline se acepta aunque llegue horas tarde, siempre que la firma
# del QR sea válida y el (empleado, qr_jti) no se haya usado antes (anti-replay).
# Casos sospechosos NO bloquean: levantan revisar_offline para RRHH.


def _flags_offline(timestamp_qr, timestamp_dispositivo, ahora) -> list:
    """Calcula los motivos de revisión RRHH (sin bloquear)."""
    motivos = []
    if timestamp_qr is not None and (ahora - timestamp_qr) > TOLERANCIA_ANTIGUEDAD:
        motivos.append("QR_ANTIGUO")
    if timestamp_qr is not None and timestamp_dispositivo is not None:
        if abs(timestamp_dispositivo - timestamp_qr) > TOLERANCIA_DESFASE_DISPOSITIVO:
            motivos.append("DESFASE_DISPOSITIVO")
    return motivos


def _resultado(estado, *, marcacion_id=None, revisar=False, motivos=None, detalle=None):
    res = {
        "estado": estado,
        "marcacion_id": marcacion_id,
        "revisar_offline": revisar,
        "motivos": motivos or [],
    }
    if detalle:
        res["detalle"] = detalle
    return res


def sincronizar_item_offline(
    *,
    empleado: Empleado,
    token_qr: str,
    tipo: str,
    latitud,
    longitud,
    timestamp_dispositivo=None,
    ip_origen: Optional[str] = None,
) -> dict:
    """Procesa UNA marcación offline (atómica, idempotente). Devuelve su estado.

    Estados: ACEPTADA, REVISAR (aceptada + bandera), DUPLICADA (replay), RECHAZADA.
    """
    # Firma del QR (sin validar antigüedad: el offline llega tarde a propósito).
    try:
        payload = validar_token_qr_offline(token_qr)
    except (TokenQRInvalido, TokenQRVencido) as exc:
        return _resultado(ESTADO_RECHAZADA, detalle=str(exc))

    sede = Sede.objects.get(pk=payload["sede_id"])
    qr_jti = payload.get("jti")
    timestamp_qr = _hora_oficial_desde_payload(payload)
    ahora = timezone.now()

    motivos = _flags_offline(timestamp_qr, timestamp_dispositivo, ahora)
    revisar = bool(motivos)
    distancia_metros, fuera_de_sede = _construir_geocerca(sede, latitud, longitud)

    with transaction.atomic():
        # Serializa las sincronizaciones del MISMO empleado (idempotencia segura).
        Empleado.objects.select_for_update().get(pk=empleado.pk)

        # Anti-replay: ¿este empleado ya consumió este QR? -> idempotente.
        existente = Marcacion.objects.filter(
            empleado=empleado, qr_jti=qr_jti
        ).first()
        if existente is not None:
            _auditar_replay(existente, empleado, qr_jti, ip_origen)
            return _resultado(
                ESTADO_DUPLICADA,
                marcacion_id=str(existente.pk),
                revisar=existente.revisar_offline,
                motivos=["REPLAY"],
            )

        try:
            with transaction.atomic():  # savepoint para aislar el IntegrityError
                marcacion = Marcacion.objects.create(
                    empleado=empleado,
                    sede=sede,
                    tipo=tipo,
                    latitud=latitud,
                    longitud=longitud,
                    fuera_de_sede=fuera_de_sede,
                    distancia_metros=distancia_metros,
                    es_offline=True,
                    revisar_offline=revisar,
                    timestamp_qr=timestamp_qr,
                    timestamp_dispositivo=timestamp_dispositivo,
                    qr_jti=qr_jti,
                )
        except IntegrityError:
            # Carrera (mismo QR) o colisión de minuto: ya hay una marcación.
            existente = Marcacion.objects.filter(
                empleado=empleado, qr_jti=qr_jti
            ).first()
            if existente is not None:
                _auditar_replay(existente, empleado, qr_jti, ip_origen)
            return _resultado(
                ESTADO_DUPLICADA,
                marcacion_id=str(existente.pk) if existente else None,
                revisar=existente.revisar_offline if existente else False,
                motivos=["REPLAY"],
            )

        AuditService.registrar(
            accion=AuditLog.Accion.MARCACION,
            entidad="Marcacion",
            entidad_id=str(marcacion.pk),
            actor_id=str(empleado.usuario_id),
            actor_rol=empleado.usuario.rol,
            ip_origen=ip_origen,
            metadata={
                "tipo": tipo,
                "sede_id": sede.pk,
                "es_offline": True,
                "revisar_offline": revisar,
                "motivos": motivos,
                "qr_jti": qr_jti,
                "timestamp_qr": timestamp_qr.isoformat() if timestamp_qr else None,
                "fuera_de_sede": fuera_de_sede,
                "distancia_metros": str(distancia_metros),
            },
        )

    return _resultado(
        ESTADO_REVISAR if revisar else ESTADO_ACEPTADA,
        marcacion_id=str(marcacion.pk),
        revisar=revisar,
        motivos=motivos,
    )


def _auditar_replay(existente: Marcacion, empleado: Empleado, qr_jti, ip_origen):
    """Registra en audit_log un intento de reuso del mismo QR (visible a RRHH).

    La marcación original es inmutable, así que el replay no la altera: queda
    constancia del intento en la auditoría.
    """
    AuditService.registrar(
        accion=AuditLog.Accion.MARCACION,
        entidad="Marcacion",
        entidad_id=str(existente.pk),
        actor_id=str(empleado.usuario_id),
        actor_rol=empleado.usuario.rol,
        ip_origen=ip_origen,
        metadata={
            "es_offline": True,
            "replay": True,
            "qr_jti": qr_jti,
            "detalle": "Reuso de un QR ya consumido (idempotencia).",
        },
    )


def sincronizar_lote(*, empleado: Empleado, items: list, ip_origen=None) -> list:
    """Procesa un LOTE de marcaciones offline. Cada ítem es independiente.

    NO se envuelve todo el lote en una sola transacción: cada ítem es atómico por
    separado, de modo que un ítem inválido no descarta a los demás.
    """
    resultados = []
    for indice, item in enumerate(items):
        resultado = sincronizar_item_offline(
            empleado=empleado,
            token_qr=item["token_qr"],
            tipo=item["tipo"],
            latitud=item["latitud"],
            longitud=item["longitud"],
            timestamp_dispositivo=item.get("timestamp_dispositivo"),
            ip_origen=ip_origen,
        )
        resultado["indice"] = indice
        resultados.append(resultado)
    return resultados
