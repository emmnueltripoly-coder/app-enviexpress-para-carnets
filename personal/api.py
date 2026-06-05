"""
Vistas API de autenticación y de usuario (Hito 2).

- LoginView: valida credenciales (username o documento) y, ante un login
  EXITOSO, registra el evento en audit_log vía AuditService (único punto
  autorizado del Hito 0).
- RefreshView: renueva el access token (simplejwt estándar).
- MeView: datos del usuario autenticado.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenRefreshView

from auditoria.models import AuditLog
from auditoria.services import AuditService
from common.utils import get_client_ip

from .serializers import LoginSerializer, UsuarioMeSerializer


class LoginView(APIView):
    """POST: credenciales -> {access, refresh}. Público. Audita el éxito."""

    permission_classes = [AllowAny]
    # Se mantiene el authenticator JWT por defecto (no se envía token al hacer
    # login, así que es inocuo). Esto permite que un fallo de credenciales
    # responda 401 con cabecera WWW-Authenticate, en lugar de 403.

    def post(self, request, *args, **kwargs):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        # Si las credenciales son inválidas, lanza 401/400 y NO se crea sesión
        # ni se registra auditoría (LOGIN se reserva para inicios exitosos).
        serializer.is_valid(raise_exception=True)

        usuario = serializer.user
        AuditService.registrar(
            accion=AuditLog.Accion.LOGIN,
            entidad="Usuario",
            entidad_id=str(usuario.pk),
            actor_id=str(usuario.pk),
            actor_rol=usuario.rol,
            ip_origen=get_client_ip(request),
            metadata={"username": usuario.get_username()},
        )
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class RefreshView(TokenRefreshView):
    """POST: {refresh} -> {access}. Público (renueva el token de acceso)."""

    permission_classes = [AllowAny]


class MeView(APIView):
    """GET: datos básicos del usuario autenticado y su rol."""

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(UsuarioMeSerializer(request.user).data)


class HealthCheckView(APIView):
    """GET: responde 200 OK. Usado por Render para verificar que el servicio está vivo."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs):
        return Response({"status": "ok"})
