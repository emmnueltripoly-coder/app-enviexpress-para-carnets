"""
AuditService — capa de servicio de auditoría.

╔════════════════════════════════════════════════════════════════════════╗
║  ESTE ES EL ÚNICO PUNTO AUTORIZADO PARA ESCRIBIR EN audit_log.          ║
║                                                                        ║
║  Ningún otro módulo debe llamar a AuditLog.objects.create() ni guardar  ║
║  instancias de AuditLog directamente. Todo registro de auditoría pasa   ║
║  por AuditService.registrar(...), de modo que exista un único lugar      ║
║  controlado, testeable y auditable donde se generan los eventos         ║
║  (requisito BASC / Ley 1581 de trazabilidad).                           ║
╚════════════════════════════════════════════════════════════════════════╝
"""

from __future__ import annotations

from typing import Any, Optional

from .models import AuditLog


class AuditService:
    """Servicio de escritura de auditoría (append-only)."""

    @staticmethod
    def registrar(
        *,
        accion: str,
        entidad: str,
        actor_id: Optional[str] = None,
        actor_rol: Optional[str] = None,
        entidad_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        ip_origen: Optional[str] = None,
    ) -> AuditLog:
        """Registra (INSERT) un evento de auditoría y devuelve la instancia creada.

        Este es el ÚNICO método autorizado para escribir en audit_log.

        Args:
            accion: Una de AuditLog.Accion (LOGIN, MARCACION, NOVEDAD_CREADA,
                NOVEDAD_APROBADA, TURNO_CAMBIADO, CONFIG_CAMBIADA,
                EXPORTACION_DATOS).
            entidad: Nombre de la entidad afectada (p. ej. "Empleado", "Marcacion").
            actor_id: Identificador del actor (usuario) que ejecuta la acción.
            actor_rol: Rol del actor en el momento de la acción.
            entidad_id: Identificador del registro afectado.
            metadata: Diccionario serializable a JSON con el contexto del evento.
            ip_origen: Dirección IP de origen de la solicitud.

        Returns:
            La instancia AuditLog persistida.
        """
        return AuditLog.objects.create(
            accion=accion,
            entidad=entidad,
            actor_id=actor_id,
            actor_rol=actor_rol,
            entidad_id=entidad_id,
            metadata=metadata if metadata is not None else {},
            ip_origen=ip_origen,
        )
