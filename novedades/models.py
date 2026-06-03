"""
Modelos de novedades (Hito 6).

Una Novedad (incapacidad, permiso, vacaciones, problema) puede llevar SOPORTES
adjuntos. Los soportes pueden ser datos sensibles de salud (Ley 1581): se
guardan en almacenamiento PRIVADO y se sirven solo por vista autenticada.

La Novedad cambia de estado (PENDIENTE -> APROBADA/RECHAZADA); cada transición
se traza en audit_log (no hay borrado físico: soft-delete vía SoftDeleteModel).
"""

import uuid

from django.conf import settings
from django.db import models

from common.models import SoftDeleteModel
from .storage import private_storage


def _ruta_soporte(instance, filename):
    # Carpeta por novedad dentro del almacenamiento privado.
    return f"soportes_novedad/{instance.novedad_id}/{filename}"


class Novedad(SoftDeleteModel):
    """Novedad reportada por un empleado (soft-delete; estado auditable)."""

    class Tipo(models.TextChoices):
        INCAPACIDAD = "INCAPACIDAD", "Incapacidad"
        PERMISO = "PERMISO", "Permiso"
        VACACIONES = "VACACIONES", "Vacaciones"
        PROBLEMA = "PROBLEMA", "Problema reportado"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADA = "APROBADA", "Aprobada"
        RECHAZADA = "RECHAZADA", "Rechazada"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    empleado = models.ForeignKey(
        "personal.Empleado",
        on_delete=models.PROTECT,
        related_name="novedades",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PENDIENTE
    )

    class Meta:
        db_table = "novedad"
        verbose_name = "Novedad"
        verbose_name_plural = "Novedades"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["empleado", "estado"]),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.empleado_id} ({self.estado})"


class SoporteNovedad(models.Model):
    """Adjunto de una novedad. Archivo en almacenamiento PRIVADO (dato sensible)."""

    novedad = models.ForeignKey(
        Novedad, on_delete=models.PROTECT, related_name="soportes"
    )
    archivo = models.FileField(upload_to=_ruta_soporte, storage=private_storage)
    nombre_original = models.CharField(max_length=255)
    tipo_mime = models.CharField(max_length=100)
    tamano_bytes = models.PositiveIntegerField(default=0)
    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="soportes_subidos",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "soporte_novedad"
        verbose_name = "Soporte de novedad"
        verbose_name_plural = "Soportes de novedad"
        ordering = ("-created_at",)

    def __str__(self):
        return f"Soporte {self.nombre_original} (novedad {self.novedad_id})"
