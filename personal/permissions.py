"""
Permisos DRF por rol (Hito 2).

Diseño del rol AUDITOR (regla no negociable: "Rol Auditor read-only"):
- ``EsSoloLectura`` permite a un AUDITOR únicamente métodos seguros
  (GET/HEAD/OPTIONS) y bloquea toda escritura (POST/PUT/PATCH/DELETE).
- Para garantizar que el AUDITOR NUNCA pueda escribir en NINGÚN endpoint
  (no solo en los que recuerden añadir el permiso), ``EsSoloLectura`` se
  registra ADEMÁS de forma GLOBAL en DEFAULT_PERMISSION_CLASSES. DRF combina
  los permisos por defecto con AND, así que la protección aplica a todo
  endpoint que no la sobreescriba explícitamente (login/refresh son públicos).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Usuario


class _RolRequerido(BasePermission):
    """Base: concede acceso solo si el usuario autenticado tiene cierto rol."""

    rol_requerido = None

    def has_permission(self, request, view):
        usuario = request.user
        return bool(
            usuario
            and usuario.is_authenticated
            and usuario.rol == self.rol_requerido
        )


class EsAdmin(_RolRequerido):
    rol_requerido = Usuario.Rol.ADMIN


class EsRRHH(_RolRequerido):
    rol_requerido = Usuario.Rol.RRHH


class EsSupervisor(_RolRequerido):
    rol_requerido = Usuario.Rol.SUPERVISOR


class EsAuditor(_RolRequerido):
    rol_requerido = Usuario.Rol.AUDITOR


class EsEmpleado(_RolRequerido):
    rol_requerido = Usuario.Rol.EMPLEADO


class EsSoloLectura(BasePermission):
    """El rol AUDITOR solo puede leer; cualquier otro rol pasa sin restricción.

    Para el AUDITOR: solo métodos seguros (GET/HEAD/OPTIONS).
    Para el resto de roles: no impone restricción (devuelve True) — la
    autorización fina la dan otros permisos por-vista.
    """

    mensaje = "El rol AUDITOR es de solo lectura: no puede realizar escrituras."
    # DRF usa el atributo 'message' para el detalle del 403.
    message = mensaje

    def has_permission(self, request, view):
        usuario = request.user
        if not (usuario and usuario.is_authenticated):
            return False
        if usuario.rol == Usuario.Rol.AUDITOR:
            return request.method in SAFE_METHODS
        return True
