"""Admin de auditoría — AuditLog es append-only, nunca editable (Hito 7)."""

from unfold.admin import ModelAdmin

from django.contrib import admin

from common.admin_mixins import AuditorReadOnlyMixin, ImmutableAdminMixin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(ImmutableAdminMixin, AuditorReadOnlyMixin, ModelAdmin):
    list_display = (
        "created_at",
        "accion",
        "entidad",
        "entidad_id",
        "actor_id",
        "actor_rol",
        "ip_origen",
    )
    list_filter = ("accion", "actor_rol")
    search_fields = ("actor_id", "entidad", "entidad_id")
    date_hierarchy = "created_at"
    readonly_fields = (
        "id",
        "created_at",
        "actor_id",
        "actor_rol",
        "accion",
        "entidad",
        "entidad_id",
        "metadata",
        "ip_origen",
    )
