"""
Permisos de reportes (Hito 8).

- ``PuedeGenerarReportes``: reportes agregados de lectura. Los pueden generar
  RRHH, Admin, Supervisor (acotado a su sede) y Auditor (su acceso queda
  auditado). Un EMPLEADO normal NO genera reportes agregados.
- ``puede_exportar_habeas_data``: la exportación individual de datos personales
  solo la puede pedir el PROPIO titular, RRHH o Admin. Un empleado nunca puede
  exportar los datos de OTRO; el auditor/supervisor tampoco exportan el
  expediente personal completo de un tercero.
"""

from rest_framework.permissions import BasePermission

from personal.models import Usuario

ROLES_REPORTES = {
    Usuario.Rol.ADMIN,
    Usuario.Rol.RRHH,
    Usuario.Rol.SUPERVISOR,
    Usuario.Rol.AUDITOR,
}


class PuedeGenerarReportes(BasePermission):
    message = "No tiene permiso para generar reportes."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(
            usuario
            and usuario.is_authenticated
            and usuario.rol in ROLES_REPORTES
        )


def puede_exportar_habeas_data(solicitante, empleado_objetivo) -> bool:
    """¿Puede ``solicitante`` exportar el expediente Habeas Data de ``empleado_objetivo``?"""
    if not (solicitante and solicitante.is_authenticated):
        return False
    # El propio titular siempre puede exportar SUS datos.
    propio = getattr(solicitante, "empleado", None)
    if propio is not None and propio.pk == empleado_objetivo.pk:
        return True
    # RRHH y Admin pueden exportar el de cualquiera.
    return solicitante.rol in {Usuario.Rol.RRHH, Usuario.Rol.ADMIN}
