"""
Modelo de auditoría append-only (BASC + Ley 1581).

Reglas no negociables aplicadas aquí:
- Log inalterable: solo se permite INSERT. Prohibido UPDATE y DELETE.
  La inmutabilidad se fuerza en DOS capas:
    1. En Python (este modelo): save() rechaza cualquier modificación y no
       existe método de borrado de negocio.
    2. En PostgreSQL (migración RunSQL): un trigger BEFORE UPDATE OR DELETE
       lanza EXCEPTION. Esta es la defensa real exigida por BASC, porque
       cubre incluso accesos directos a la BD que evadan el ORM.
- Inmutable: el modelo NO tiene campos updated_at ni deleted_at.
- Trazabilidad temporal: created_at en UTC (USE_TZ=True).
"""

import uuid

from django.db import models


class AuditLog(models.Model):
    """Registro inmutable de una acción sensible del sistema (append-only)."""

    class Accion(models.TextChoices):
        LOGIN = "LOGIN", "Inicio de sesión"
        MARCACION = "MARCACION", "Marcación"
        NOVEDAD_CREADA = "NOVEDAD_CREADA", "Novedad creada"
        NOVEDAD_APROBADA = "NOVEDAD_APROBADA", "Novedad aprobada"
        TURNO_CAMBIADO = "TURNO_CAMBIADO", "Turno cambiado"
        CONFIG_CAMBIADA = "CONFIG_CAMBIADA", "Configuración cambiada"
        EXPORTACION_DATOS = "EXPORTACION_DATOS", "Exportación de datos"
        # Hito 1 (Identidad): acciones aditivas para el rastro BASC de
        # gestión de personal y Habeas Data. El trigger append-only no cambia.
        EMPLEADO_CREADO = "EMPLEADO_CREADO", "Empleado creado"
        CONSENTIMIENTO_REGISTRADO = "CONSENTIMIENTO_REGISTRADO", "Consentimiento Habeas Data registrado"
        # Hito 6 (Novedades): rechazo de novedad y acceso a soportes sensibles
        # (datos de salud, Ley 1581). Aditivo; el trigger append-only no cambia.
        NOVEDAD_RECHAZADA = "NOVEDAD_RECHAZADA", "Novedad rechazada"
        SOPORTE_ACCEDIDO = "SOPORTE_ACCEDIDO", "Soporte de novedad accedido"

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    # auto_now_add => se fija en la creación y no es editable. Siempre en UTC.
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        db_index=True,
    )
    # Identidad del actor. Nullable: hay acciones del sistema sin usuario.
    actor_id = models.CharField(max_length=255, null=True, blank=True)
    actor_rol = models.CharField(max_length=50, null=True, blank=True)

    accion = models.CharField(max_length=32, choices=Accion.choices)

    entidad = models.CharField(max_length=100)
    entidad_id = models.CharField(max_length=255, null=True, blank=True)

    # Contexto estructurado de la acción (qué cambió, valores, etc.).
    metadata = models.JSONField(default=dict, blank=True)

    ip_origen = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_log"
        verbose_name = "Registro de auditoría"
        verbose_name_plural = "Registros de auditoría"
        ordering = ("-created_at",)

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S%z}] {self.accion} {self.entidad}"

    def save(self, *args, **kwargs):
        """Append-only: permite el INSERT inicial pero rechaza cualquier edición.

        Nota: como ``id`` usa ``default=uuid.uuid4``, la pk ya está poblada en
        memoria antes del primer guardado, por lo que NO basta con comprobar
        ``self.pk``. Usamos ``self._state.adding``, que solo es True mientras el
        objeto aún no ha sido persistido. Tras el primer save() pasa a False, de
        modo que un segundo save() (un UPDATE) queda bloqueado.
        """
        if not self._state.adding:
            raise ValueError(
                "AuditLog es append-only: un registro de auditoría no puede "
                "modificarse una vez creado."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Append-only: prohibido borrar registros de auditoría."""
        raise ValueError(
            "AuditLog es append-only: un registro de auditoría no puede borrarse."
        )
