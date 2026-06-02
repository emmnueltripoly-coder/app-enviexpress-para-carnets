"""
Modelos de organización: Empresa y Sede.

La Sede incluye los parámetros de geocerca (latitud, longitud, radio) que el
Hito 3 (marcación) usará para validar la ubicación del empleado al marcar.
"""

from django.db import models

from common.models import SoftDeleteModel


class Empresa(SoftDeleteModel):
    """Empresa (cliente con certificación BASC). Soft-delete vía ``activo``."""

    nombre = models.CharField(max_length=200)
    # NIT colombiano: identificador tributario único de la empresa.
    nit = models.CharField(max_length=20, unique=True)

    class Meta:
        db_table = "empresa"
        verbose_name = "Empresa"
        verbose_name_plural = "Empresas"
        ordering = ("nombre",)

    def __str__(self):
        return f"{self.nombre} (NIT {self.nit})"


class Sede(SoftDeleteModel):
    """Sede física de una empresa. Define la geocerca para la marcación."""

    class Ciudad(models.TextChoices):
        MEDELLIN = "MEDELLIN", "Medellín"
        CALI = "CALI", "Cali"
        BOGOTA = "BOGOTA", "Bogotá"
        BARRANQUILLA = "BARRANQUILLA", "Barranquilla"

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.PROTECT,  # no borrado físico en cascada (BASC)
        related_name="sedes",
    )
    nombre = models.CharField(max_length=200)
    ciudad = models.CharField(max_length=20, choices=Ciudad.choices)
    direccion = models.CharField(max_length=255)

    # Geocerca: centro (lat/lon) + radio de tolerancia en metros.
    # 9 dígitos y 6 decimales => precisión ~0.11 m, suficiente para geocerca.
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)
    radio_metros = models.PositiveIntegerField(default=100)

    class Meta:
        db_table = "sede"
        verbose_name = "Sede"
        verbose_name_plural = "Sedes"
        ordering = ("empresa__nombre", "nombre")

    def __str__(self):
        return f"{self.nombre} — {self.get_ciudad_display()}"
