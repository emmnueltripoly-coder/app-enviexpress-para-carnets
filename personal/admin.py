from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ConsentimientoHabeasData, Empleado, Usuario


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    # Extiende el UserAdmin estándar añadiendo el campo 'rol'.
    list_display = ("username", "rol", "email", "is_active", "is_staff")
    list_filter = ("rol", "is_active", "is_staff")
    fieldsets = UserAdmin.fieldsets + (("Rol", {"fields": ("rol",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Rol", {"fields": ("rol",)}),)


@admin.register(Empleado)
class EmpleadoAdmin(admin.ModelAdmin):
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
class ConsentimientoHabeasDataAdmin(admin.ModelAdmin):
    # Registro inmutable: en el admin es solo lectura (no se edita ni se borra).
    list_display = ("empleado", "version_politica", "aceptado", "fecha_aceptacion")
    list_filter = ("aceptado", "version_politica")
    search_fields = ("empleado__documento_identidad", "empleado__apellidos")

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
