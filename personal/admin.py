"""Admin de personal (Hito 7).

- UsuarioAdmin: gestión de usuarios + roles; AUDITOR no puede escribir.
- EmpleadoAdmin: Supervisor ve solo su sede.
- ConsentimientoHabeasDataAdmin: inmutable (Ley 1581).
"""

from unfold.admin import ModelAdmin

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from common.admin_mixins import AuditorReadOnlyMixin, ImmutableAdminMixin, SedeFilterMixin

from .models import ConsentimientoHabeasData, Empleado, Usuario


@admin.register(Usuario)
class UsuarioAdmin(AuditorReadOnlyMixin, ModelAdmin, BaseUserAdmin):
    list_display = ("username", "rol", "email", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (("Rol", {"fields": ("rol",)}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("Rol", {"fields": ("rol",)}),)


@admin.register(Empleado)
class EmpleadoAdmin(SedeFilterMixin, AuditorReadOnlyMixin, ModelAdmin):
    sede_filter_field = "sede_id"

    list_display = (
        "documento_identidad",
        "nombres",
        "apellidos",
        "sede",
        "cargo",
        "activo",
        "created_at",
    )
    list_filter = ("activo", "sede", "sede__ciudad")
    search_fields = ("documento_identidad", "nombres", "apellidos")
    autocomplete_fields = ("usuario", "sede")


@admin.register(ConsentimientoHabeasData)
class ConsentimientoHabeasDataAdmin(ImmutableAdminMixin, AuditorReadOnlyMixin, ModelAdmin):
    list_display = ("empleado", "version_politica", "aceptado", "fecha_aceptacion")
    list_filter = ("aceptado", "version_politica")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")
    readonly_fields = (
        "empleado",
        "version_politica",
        "aceptado",
        "fecha_aceptacion",
        "ip_aceptacion",
        "texto_politica",
        "created_at",
    )
