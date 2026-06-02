from django.contrib import admin

from .models import Empresa, Sede


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    list_display = ("nombre", "nit", "activo", "created_at")
    list_filter = ("activo",)
    search_fields = ("nombre", "nit")


@admin.register(Sede)
class SedeAdmin(admin.ModelAdmin):
    list_display = ("nombre", "empresa", "ciudad", "radio_metros", "activo", "created_at")
    list_filter = ("ciudad", "activo", "empresa")
    search_fields = ("nombre", "direccion")
