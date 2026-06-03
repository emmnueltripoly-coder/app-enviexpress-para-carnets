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

from decimal import Decimal, ROUND_HALF_UP
from math import asin, cos, radians, sin, sqrt
from typing import Optional

from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone

from auditoria.models import AuditLog
from auditoria.services import AuditService
from organizacion.models import Sede
from personal.models import Empleado

from .models import Marcacion

# Vigencia del QR del kiosco (segundos) y sal de firma.
QR_MAX_AGE_SEGUNDOS = 45
QR_SALT = "kiosco-qr-marcacion-v1"

# Ventana (segundos) para la verificación amigable de doble-marcación previa al
# INSERT. La garantía dura la da la ExclusionConstraint de la BD.
VENTANA_ANTIDUPLICADO_SEGUNDOS = 60

RADIO_TIERRA_METROS = 6_371_000


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
def generar_token_qr(sede_id: int) -> str:
    """Devuelve un token firmado (SECRET_KEY) que codifica la sede + timestamp."""
    return signing.dumps({"sede_id": sede_id}, salt=QR_SALT, compress=True)


def validar_token_qr(token: str) -> int:
    """Valida firma y vigencia del token; devuelve el sede_id.

    Lanza TokenQRVencido si expiró y TokenQRInvalido si la firma es inválida.
    """
    try:
        datos = signing.loads(
            token, salt=QR_SALT, max_age=QR_MAX_AGE_SEGUNDOS
        )
    except signing.SignatureExpired:
        raise TokenQRVencido(
            "El código QR venció. Solicite uno nuevo en el kiosco."
        )
    except signing.BadSignature:
        raise TokenQRInvalido("El código QR no es válido.")
    return datos["sede_id"]


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
    # (a) Token
    sede_id = validar_token_qr(token_qr)
    sede = Sede.objects.get(pk=sede_id)

    # (b) Geocerca flexible (no bloquea; marca para revisión)
    distancia_metros, fuera_de_sede = _construir_geocerca(sede, latitud, longitud)

    # (c) Inserción anti-duplicado.
    # select_for_update serializa las peticiones del MISMO empleado, de modo que
    # ante dos llamadas concurrentes la segunda vea la primera y devuelva un
    # error amigable. La ExclusionConstraint es la garantía dura final.
    Empleado.objects.select_for_update().get(pk=empleado.pk)

    limite = timezone.now() - timezone.timedelta(seconds=VENTANA_ANTIDUPLICADO_SEGUNDOS)
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
