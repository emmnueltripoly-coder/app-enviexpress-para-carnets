"""
Servicios de novedades (Hito 6): creación + notificación email, adjuntar
soporte, transiciones de estado y registro de acceso a soportes.

Toda acción sensible se audita vía AuditService (único punto del Hito 0). El
contenido de salud NUNCA viaja por email ni se expone en URLs públicas.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger(__name__)

from auditoria.models import AuditLog
from auditoria.services import AuditService
from personal.models import Empleado

from .models import Novedad, SoporteNovedad


# --------------------------------------------------------------------------
# Creación + notificación
# --------------------------------------------------------------------------
def _notificar_rrhh(novedad: Novedad) -> None:
    """Avisa a RRHH de una novedad nueva SIN exponer datos sensibles.

    El correo incluye solo un resumen (empleado, tipo, fechas). NO incluye la
    descripción ni el contenido de los soportes (dato de salud, Ley 1581).
    """
    destinatarios = getattr(settings, "NOVEDADES_EMAILS", [])
    if not destinatarios:
        return

    empleado = novedad.empleado
    asunto = f"[Novedad] {novedad.get_tipo_display()} — {empleado.nombre_completo}"
    cuerpo = (
        "Se registró una nueva novedad que requiere gestión.\n\n"
        f"Empleado: {empleado.nombre_completo} (documento {empleado.documento_identidad})\n"
        f"Sede: {empleado.sede}\n"
        f"Tipo: {novedad.get_tipo_display()}\n"
        f"Fecha inicio: {novedad.fecha_inicio}\n"
        f"Fecha fin: {novedad.fecha_fin or 'N/D'}\n"
        f"Estado: {novedad.get_estado_display()}\n\n"
        "Por seguridad y protección de datos (Ley 1581), el detalle y los "
        "soportes adjuntos NO se incluyen en este correo: ingrese al panel para "
        "consultarlos.\n"
    )
    try:
        send_mail(
            asunto,
            cuerpo,
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            fail_silently=False,
        )
        logger.info("Notificación de novedad enviada a %s", destinatarios)
    except Exception:
        logger.exception(
            "Error al enviar notificación de novedad %s a RRHH. "
            "La novedad se creó correctamente pero el aviso no llegó.",
            novedad.pk,
        )


@transaction.atomic
def crear_novedad(
    *,
    empleado: Empleado,
    tipo: str,
    descripcion: str,
    fecha_inicio,
    fecha_fin=None,
    ip_origen: Optional[str] = None,
) -> Novedad:
    """Crea una novedad PENDIENTE, la audita (NOVEDAD_CREADA) y notifica a RRHH."""
    novedad = Novedad.objects.create(
        empleado=empleado,
        tipo=tipo,
        descripcion=descripcion,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    AuditService.registrar(
        accion=AuditLog.Accion.NOVEDAD_CREADA,
        entidad="Novedad",
        entidad_id=str(novedad.pk),
        actor_id=str(empleado.usuario_id),
        actor_rol=empleado.usuario.rol,
        ip_origen=ip_origen,
        metadata={"tipo": tipo, "empleado_id": empleado.pk},
    )
    # El email se envía tras confirmar la transacción (evita avisar si hace rollback).
    transaction.on_commit(lambda: _notificar_rrhh(novedad))
    return novedad


# --------------------------------------------------------------------------
# Soportes
# --------------------------------------------------------------------------
@transaction.atomic
def adjuntar_soporte(*, novedad: Novedad, archivo, usuario) -> SoporteNovedad:
    """Adjunta un soporte ya validado a una novedad."""
    return SoporteNovedad.objects.create(
        novedad=novedad,
        archivo=archivo,
        nombre_original=archivo.name,
        tipo_mime=getattr(archivo, "content_type", "") or "",
        tamano_bytes=archivo.size,
        subido_por=usuario,
    )


def registrar_acceso_soporte(*, soporte: SoporteNovedad, usuario, modo: str, ip_origen=None):
    """Audita el acceso a un soporte sensible (quién, a qué, en qué modo)."""
    AuditService.registrar(
        accion=AuditLog.Accion.SOPORTE_ACCEDIDO,
        entidad="SoporteNovedad",
        entidad_id=str(soporte.pk),
        actor_id=str(usuario.pk),
        actor_rol=usuario.rol,
        ip_origen=ip_origen,
        metadata={
            "novedad_id": str(soporte.novedad_id),
            "empleado_id": soporte.novedad.empleado_id,
            "modo": modo,  # 'descarga' | 'metadatos'
            "nombre_original": soporte.nombre_original,
        },
    )


# --------------------------------------------------------------------------
# Transiciones de estado (auditadas)
# --------------------------------------------------------------------------
@transaction.atomic
def cambiar_estado(
    *,
    novedad: Novedad,
    nuevo_estado: str,
    usuario,
    comentario: str = "",
    ip_origen: Optional[str] = None,
) -> Novedad:
    """Cambia el estado de una novedad y registra la transición en audit_log."""
    estado_anterior = novedad.estado
    novedad.estado = nuevo_estado
    novedad.save(update_fields=["estado"])

    accion = (
        AuditLog.Accion.NOVEDAD_APROBADA
        if nuevo_estado == Novedad.Estado.APROBADA
        else AuditLog.Accion.NOVEDAD_RECHAZADA
    )
    AuditService.registrar(
        accion=accion,
        entidad="Novedad",
        entidad_id=str(novedad.pk),
        actor_id=str(usuario.pk),
        actor_rol=usuario.rol,
        ip_origen=ip_origen,
        metadata={
            "estado_anterior": estado_anterior,
            "estado_nuevo": nuevo_estado,
            "comentario": comentario,
        },
    )
    return novedad
