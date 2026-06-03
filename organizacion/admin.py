"""Admin de organizacion (Hito 7)."""

from unfold.admin import ModelAdmin

from django.contrib import admin

from common.admin_mixins import AuditorReadOnlyMixin

from .models import Empresa, Sede


@admin.register(Empresa)
class EmpresaAdmin(AuditorReadOnlyMixin, ModelAdmin):
    list_display = ("nombre", "nit", "activo", "created_at")
    list_filter = ("activo",)
    search_fields = ("nombre", "nit")


@admin.register(Sede)
class SedeAdmin(AuditorReadOnlyMixin, ModelAdmin):
    list_display = ("nombre", "empresa", "ciudad", "radio_metros", "activo", "created_at")
    list_filter = ("ciudad", "activo", "empresa")
    search_fields = ("nombre", "direccion")
