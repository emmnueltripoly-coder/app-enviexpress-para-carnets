from django.contrib import admin

from .models import Marcacion


@admin.register(Marcacion)
class MarcacionAdmin(admin.ModelAdmin):
    # Marcación inmutable: el admin la muestra en SOLO LECTURA (no edita/borra).
    list_display = (
        "id",
        "empleado",
        "sede",
        "tipo",
        "timestamp_servidor",
        "fuera_de_sede",
        "distancia_metros",
        "es_offline",
        "corrige_a",
    )
    list_filter = ("tipo", "fuera_de_sede", "es_offline", "sede")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    date_hierarchy = "timestamp_servidor"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
