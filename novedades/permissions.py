"""
Autorización por objeto para novedades y soportes (datos sensibles, Ley 1581).

Reglas:
- Gestionar (aprobar/rechazar, ver ámbito): RRHH, Admin, o Supervisor de la sede
  del empleado dueño de la novedad.
- Ver/descargar el CONTENIDO de un soporte: el dueño o un gestor. El AUDITOR NO
  accede al contenido (es dato de salud); solo a metadatos.
- Ver METADATOS de un soporte: dueño, gestores y AUDITOR.
"""

from personal.models import Usuario


def es_dueno(usuario, novedad) -> bool:
    empleado = getattr(usuario, "empleado", None)
    return empleado is not None and novedad.empleado_id == empleado.pk


def puede_gestionar(usuario, novedad) -> bool:
    """RRHH/Admin, o Supervisor de la sede del empleado dueño."""
    if not (usuario and usuario.is_authenticated):
        return False
    if usuario.rol in {Usuario.Rol.RRHH, Usuario.Rol.ADMIN}:
        return True
    if usuario.rol == Usuario.Rol.SUPERVISOR:
        empleado = getattr(usuario, "empleado", None)
        return (
            empleado is not None
            and empleado.sede_id == novedad.empleado.sede_id
        )
    return False


def puede_ver_contenido_soporte(usuario, novedad) -> bool:
    """Contenido del archivo: dueño o gestor (NO auditor)."""
    return es_dueno(usuario, novedad) or puede_gestionar(usuario, novedad)


def puede_ver_metadatos_soporte(usuario, novedad) -> bool:
    """Metadatos: dueño, gestores y AUDITOR (su acceso queda registrado)."""
    if usuario and usuario.is_authenticated and usuario.rol == Usuario.Rol.AUDITOR:
        return True
    return puede_ver_contenido_soporte(usuario, novedad)
