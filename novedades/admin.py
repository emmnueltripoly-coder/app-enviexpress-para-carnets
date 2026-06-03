"""Admin de novedades (Hito 7).

Las acciones de aprobar/rechazar invocan la lógica del servicio del Hito 6
(que audita la transición). El AUDITOR ve todo pero no puede realizar acciones.
Soporte sensible: el admin muestra metadatos, no expone descarga directa.
Supervisor ve solo novedades de su sede.
"""

from unfold.admin import ModelAdmin

from django.contrib import admin, messages
from django.utils.translation import ngettext

from common.admin_mixins import AuditorReadOnlyMixin, ImmutableAdminMixin, SedeFilterMixin

from .models import Novedad, SoporteNovedad
from .services import cambiar_estado


def _aprobar_novedades(modeladmin, request, queryset):
    pendientes = queryset.filter(estado=Novedad.Estado.PENDIENTE)
    count = 0
    for novedad in pendientes.select_related("empleado"):
        cambiar_estado(
            novedad=novedad,
            nuevo_estado=Novedad.Estado.APROBADA,
            usuario=request.user,
            comentario="Aprobado en masa desde el panel admin.",
            ip_origen=request.META.get("REMOTE_ADDR"),
        )
        count += 1
    modeladmin.message_user(
        request,
        ngettext(
            "%d novedad aprobada.",
            "%d novedades aprobadas.",
            count,
        ) % count,
        messages.SUCCESS,
    )


_aprobar_novedades.short_description = "Aprobar novedades seleccionadas"


def _rechazar_novedades(modeladmin, request, queryset):
    pendientes = queryset.filter(estado=Novedad.Estado.PENDIENTE)
    count = 0
    for novedad in pendientes.select_related("empleado"):
        cambiar_estado(
            novedad=novedad,
            nuevo_estado=Novedad.Estado.RECHAZADA,
            usuario=request.user,
            comentario="Rechazado en masa desde el panel admin.",
            ip_origen=request.META.get("REMOTE_ADDR"),
        )
        count += 1
    modeladmin.message_user(
        request,
        ngettext(
            "%d novedad rechazada.",
            "%d novedades rechazadas.",
            count,
        ) % count,
        messages.SUCCESS,
    )


_rechazar_novedades.short_description = "Rechazar novedades seleccionadas"


@admin.register(Novedad)
class NovedadAdmin(SedeFilterMixin, AuditorReadOnlyMixin, ModelAdmin):
    sede_filter_field = "empleado__sede_id"

    list_display = ("id", "empleado", "tipo", "estado", "fecha_inicio", "fecha_fin", "activo", "created_at")
    list_filter = ("tipo", "estado", "activo")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    date_hierarchy = "created_at"
    actions = [_aprobar_novedades, _rechazar_novedades]

    def get_actions(self, request):
        actions = super().get_actions(request)
        if getattr(request.user, "rol", None) not in {
            "RRHH", "ADMIN", "SUPERVISOR"
        }:
            actions.pop(_aprobar_novedades.__name__, None)
            actions.pop(_rechazar_novedades.__name__, None)
        return actions


@admin.register(SoporteNovedad)
class SoporteNovedadAdmin(ImmutableAdminMixin, AuditorReadOnlyMixin, ModelAdmin):
    list_display = ("id", "novedad", "nombre_original", "tipo_mime", "tamano_bytes", "subido_por", "created_at")
    search_fields = ("nombre_original",)
    readonly_fields = ("archivo", "nombre_original", "tipo_mime", "tamano_bytes", "subido_por", "created_at")
