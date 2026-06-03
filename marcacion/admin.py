"""Admin de marcaciones (Hito 7).

Marcación es INMUTABLE — nunca se edita ni se borra desde el admin.
Filtros especiales: fuera_de_sede y revisar_offline para supervisión operativa.
Supervisor ve solo su sede.
"""

from unfold.admin import ModelAdmin

from django.contrib import admin

from common.admin_mixins import AuditorReadOnlyMixin, ImmutableAdminMixin, SedeFilterMixin
from reportes.admin_actions import (
    exportar_asistencia_excel,
    exportar_asistencia_pdf,
    exportar_excepciones_excel,
)

from .models import Marcacion


@admin.register(Marcacion)
class MarcacionAdmin(SedeFilterMixin, ImmutableAdminMixin, AuditorReadOnlyMixin, ModelAdmin):
    sede_filter_field = "sede_id"
    actions = [
        exportar_asistencia_excel,
        exportar_asistencia_pdf,
        exportar_excepciones_excel,
    ]

    list_display = (
        "id",
        "empleado",
        "sede",
        "tipo",
        "timestamp_qr",
        "timestamp_servidor",
        "fuera_de_sede",
        "distancia_metros",
        "es_offline",
        "revisar_offline",
        "corrige_a",
    )
    list_filter = (
        "tipo",
        "fuera_de_sede",
        "es_offline",
        "revisar_offline",
        "sede",
    )
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    date_hierarchy = "timestamp_servidor"
    readonly_fields = (
        "id",
        "empleado",
        "sede",
        "tipo",
        "timestamp_qr",
        "timestamp_dispositivo",
        "timestamp_servidor",
        "minuto_marcacion",
        "fuera_de_sede",
        "distancia_metros",
        "es_offline",
        "revisar_offline",
        "qr_jti",
        "corrige_a",
    )
