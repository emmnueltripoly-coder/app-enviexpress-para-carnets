"""
Servicios de la app personal.

Encapsulan las operaciones de negocio que deben dejar rastro de auditoría.
Cada operación que escribe datos sensibles + su registro en ``audit_log`` se
ejecuta dentro de una transacción atómica: o se persisten ambas cosas, o
ninguna. La auditoría se escribe SIEMPRE a través de ``AuditService``
(único punto autorizado del Hito 0).
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from django.db import transaction
from django.utils import timezone

from auditoria.models import AuditLog
from auditoria.services import AuditService

from .models import ConsentimientoHabeasData, Empleado, Usuario


@transaction.atomic
def crear_empleado_con_usuario(
    *,
    username: str,
    password: str,
    rol: str,
    documento_identidad: str,
    nombres: str,
    apellidos: str,
    sede,
    cargo: str,
    fecha_ingreso: date,
    email: str = "",
    actor_id: Optional[str] = None,
    actor_rol: Optional[str] = None,
    ip_origen: Optional[str] = None,
) -> Empleado:
    """Crea un Usuario + su Empleado y registra la acción en audit_log.

    Todo ocurre en una sola transacción. Devuelve el Empleado creado.
    """
    usuario = Usuario.objects.create_user(
        username=username,
        password=password,
        email=email,
        rol=rol,
    )
    empleado = Empleado.objects.create(
        usuario=usuario,
        documento_identidad=documento_identidad,
        nombres=nombres,
        apellidos=apellidos,
        sede=sede,
        cargo=cargo,
        fecha_ingreso=fecha_ingreso,
    )

    AuditService.registrar(
        accion=AuditLog.Accion.EMPLEADO_CREADO,
        entidad="Empleado",
        entidad_id=str(empleado.pk),
        actor_id=actor_id,
        actor_rol=actor_rol,
        ip_origen=ip_origen,
        metadata={
            "usuario_id": usuario.pk,
            "username": usuario.username,
            "rol": usuario.rol,
            "sede_id": sede.pk,
            "cargo": cargo,
        },
    )
    return empleado


@transaction.atomic
def registrar_consentimiento(
    *,
    empleado: Empleado,
    version_politica: str,
    texto_politica: str,
    aceptado: bool,
    ip_aceptacion: str,
    fecha_aceptacion=None,
    actor_id: Optional[str] = None,
    actor_rol: Optional[str] = None,
) -> ConsentimientoHabeasData:
    """Registra un ConsentimientoHabeasData y lo deja en audit_log.

    Si no se pasa ``fecha_aceptacion`` se usa el ahora (UTC). El actor por
    defecto es el propio titular (el empleado), salvo que se indique otro.
    """
    consentimiento = ConsentimientoHabeasData.objects.create(
        empleado=empleado,
        version_politica=version_politica,
        texto_politica=texto_politica,
        aceptado=aceptado,
        ip_aceptacion=ip_aceptacion,
        fecha_aceptacion=fecha_aceptacion or timezone.now(),
    )

    AuditService.registrar(
        accion=AuditLog.Accion.CONSENTIMIENTO_REGISTRADO,
        entidad="ConsentimientoHabeasData",
        entidad_id=str(consentimiento.pk),
        actor_id=actor_id if actor_id is not None else str(empleado.usuario_id),
        actor_rol=actor_rol if actor_rol is not None else empleado.usuario.rol,
        ip_origen=ip_aceptacion,
        metadata={
            "empleado_id": empleado.pk,
            "version_politica": version_politica,
            "aceptado": aceptado,
        },
    )
    return consentimiento
