"""Serializers de autenticación y de datos del usuario (Hito 2)."""

from django.contrib.auth import authenticate
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Empleado, Usuario


class LoginSerializer(serializers.Serializer):
    """Valida credenciales aceptando ``username`` O ``documento_identidad``.

    Devuelve los tokens ``access`` y ``refresh``. El token incluye el ``rol``
    como claim para que el cliente lo conozca sin otra llamada.
    """

    username = serializers.CharField(required=False)
    documento_identidad = serializers.CharField(required=False)
    password = serializers.CharField(
        write_only=True, style={"input_type": "password"}
    )

    default_error_messages = {
        "sin_identificador": "Debe enviar 'username' o 'documento_identidad'.",
        "credenciales": "Credenciales inválidas.",
    }

    def validate(self, attrs):
        username = attrs.get("username")
        documento = attrs.get("documento_identidad")
        password = attrs["password"]

        if not username and not documento:
            raise serializers.ValidationError(
                self.error_messages["sin_identificador"], code="sin_identificador"
            )

        # Resolver el username a partir del documento (dato personal en Empleado).
        if documento and not username:
            try:
                empleado = Empleado.objects.select_related("usuario").get(
                    documento_identidad=documento
                )
                username = empleado.usuario.get_username()
            except Empleado.DoesNotExist:
                username = None

        usuario = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )
        # Mensaje genérico: no revelar si falló el identificador o la clave.
        if usuario is None:
            raise AuthenticationFailed(
                self.error_messages["credenciales"], code="credenciales"
            )

        refresh = RefreshToken.for_user(usuario)
        refresh["rol"] = usuario.rol

        # Se expone el usuario para que la vista registre la auditoría del login.
        self.user = usuario
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }


class UsuarioMeSerializer(serializers.ModelSerializer):
    """Datos básicos del usuario autenticado + su rol (endpoint /api/me)."""

    rol_display = serializers.CharField(source="get_rol_display", read_only=True)
    documento_identidad = serializers.SerializerMethodField()
    nombre_completo = serializers.SerializerMethodField()

    class Meta:
        model = Usuario
        fields = (
            "id",
            "username",
            "email",
            "rol",
            "rol_display",
            "documento_identidad",
            "nombre_completo",
        )

    def _empleado(self, obj):
        return getattr(obj, "empleado", None)

    def get_documento_identidad(self, obj):
        empleado = self._empleado(obj)
        return empleado.documento_identidad if empleado else None

    def get_nombre_completo(self, obj):
        empleado = self._empleado(obj)
        return empleado.nombre_completo if empleado else None
