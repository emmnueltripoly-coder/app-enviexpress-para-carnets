from django.contrib import admin

from .models import Novedad, SoporteNovedad


@admin.register(Novedad)
class NovedadAdmin(admin.ModelAdmin):
    list_display = ("id", "empleado", "tipo", "estado", "fecha_inicio", "fecha_fin", "activo", "created_at")
    list_filter = ("tipo", "estado", "activo")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    date_hierarchy = "created_at"


@admin.register(SoporteNovedad)
class SoporteNovedadAdmin(admin.ModelAdmin):
    # Soporte sensible: el admin muestra metadatos, no expone descarga directa.
    list_display = ("id", "novedad", "nombre_original", "tipo_mime", "tamano_bytes", "subido_por", "created_at")
    search_fields = ("nombre_original",)
    readonly_fields = ("archivo", "nombre_original", "tipo_mime", "tamano_bytes", "subido_por", "created_at")
