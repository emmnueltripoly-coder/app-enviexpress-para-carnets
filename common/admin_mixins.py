"""
Mixins reutilizables para el panel de administración (Hito 7).

- AuditorReadOnlyMixin: bloquea toda escritura para el rol AUDITOR.
- ImmutableAdminMixin: modelo que nunca se edita ni se borra (marcaciones, logs).
- SedeFilterMixin: restringe el queryset de Supervisor a su propia sede.
"""

from personal.models import Usuario


class AuditorReadOnlyMixin:
    """El rol AUDITOR puede ver todo en el admin pero no puede escribir nada."""

    def has_add_permission(self, request):
        if getattr(request.user, "rol", None) == Usuario.Rol.AUDITOR:
            return False
        return super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        if getattr(request.user, "rol", None) == Usuario.Rol.AUDITOR:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if getattr(request.user, "rol", None) == Usuario.Rol.AUDITOR:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        """El AUDITOR no recibe ninguna acción de escritura."""
        if getattr(request.user, "rol", None) == Usuario.Rol.AUDITOR:
            return {}
        return super().get_actions(request)


class ImmutableAdminMixin:
    """Modelo que NUNCA debe editarse ni borrarse desde el admin (p. ej. AuditLog, Marcacion)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class SedeFilterMixin:
    """Restringe el queryset al Supervisor para mostrar solo los registros de su sede.

    La subclase debe implementar `_get_sede_id(obj)` para determinar qué campo
    de ForeignKey lleva a la sede del objeto.  Si no lo implementa, no filtra.
    """

    sede_filter_field = None  # p. ej. "empleado__sede_id" o "sede_id"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if (
            getattr(request.user, "rol", None) == Usuario.Rol.SUPERVISOR
            and self.sede_filter_field
        ):
            empleado_supervisor = getattr(request.user, "empleado", None)
            if empleado_supervisor:
                qs = qs.filter(
                    **{self.sede_filter_field: empleado_supervisor.sede_id}
                )
        return qs
