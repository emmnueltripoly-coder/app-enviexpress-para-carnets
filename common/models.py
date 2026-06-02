"""
Abstracciones compartidas (común a todas las apps de negocio).

Soft-delete (CLAUDE.md, regla no negociable "Sin borrado físico"):
ninguna entidad de negocio se borra físicamente; se marca inactiva con
``activo=False`` mediante ``desactivar()``. El borrado físico queda reservado
únicamente para solicitudes legales de supresión de datos personales
(Ley 1581), que se abordarán en un hito posterior.
"""

from django.db import models


class ActivosManager(models.Manager):
    """Manager que devuelve solo los registros activos (no dados de baja)."""

    def get_queryset(self):
        return super().get_queryset().filter(activo=True)


class SoftDeleteModel(models.Model):
    """Base abstracta con soft-delete y marca temporal de creación.

    Expone DOS managers:
      - ``objects``: todos los registros (activos e inactivos). Sigue siendo el
        manager por defecto para no ocultar datos a Django Admin ni a auditoría.
      - ``activos``: solo los registros con ``activo=True``.
    """

    activo = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager()
    activos = ActivosManager()

    class Meta:
        abstract = True

    def desactivar(self):
        """Soft-delete: marca el registro como inactivo SIN borrarlo físicamente."""
        if self.activo:
            self.activo = False
            self.save(update_fields=["activo"])

    def activar(self):
        """Revierte un soft-delete: vuelve a marcar el registro como activo."""
        if not self.activo:
            self.activo = True
            self.save(update_fields=["activo"])
