from django.contrib import admin

from .models import (
    AsignacionTurno,
    DiaFestivo,
    ParametrosLaborales,
    ResumenJornada,
    Turno,
)


@admin.register(Turno)
class TurnoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "hora_inicio", "hora_fin", "cruza_medianoche", "sede", "activo")
    list_filter = ("cruza_medianoche", "activo", "sede")
    search_fields = ("nombre",)


@admin.register(AsignacionTurno)
class AsignacionTurnoAdmin(admin.ModelAdmin):
    list_display = ("empleado", "turno", "fecha_inicio", "fecha_fin", "activo")
    list_filter = ("activo", "turno")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    autocomplete_fields = ("empleado", "turno")


@admin.register(ParametrosLaborales)
class ParametrosLaboralesAdmin(admin.ModelAdmin):
    list_display = (
        "vigente_desde",
        "inicio_jornada_nocturna",
        "fin_jornada_nocturna",
        "horas_jornada_ordinaria_diaria",
        "porcentaje_recargo_nocturno",
    )
    ordering = ("-vigente_desde",)


@admin.register(DiaFestivo)
class DiaFestivoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "descripcion")
    search_fields = ("descripcion",)
    date_hierarchy = "fecha"


@admin.register(ResumenJornada)
class ResumenJornadaAdmin(admin.ModelAdmin):
    # Derivado y recalculable; en el admin solo lectura para evitar ediciones manuales.
    list_display = (
        "empleado",
        "fecha",
        "horas_ordinarias",
        "horas_extra_diurnas",
        "horas_extra_nocturnas",
        "horas_recargo_nocturno",
        "horas_dominical_festivo",
        "tardanza_minutos",
        "calculado_at",
    )
    list_filter = ("fecha",)
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    date_hierarchy = "fecha"

    def has_change_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False
