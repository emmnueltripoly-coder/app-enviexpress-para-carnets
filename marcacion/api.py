"""
Vistas API de marcación (Hito 3).

- QRKioscoView (GET): devuelve el token QR firmado de una sede. Solo personal de
  sede (ADMIN/RRHH/SUPERVISOR); NUNCA empleados ni auditores.
- MarcacionCreateView (POST): el empleado autenticado marca. Usa los permisos
  globales (IsAuthenticated + EsSoloLectura), por lo que el AUDITOR recibe 403.
- CorreccionView (POST): RRHH/Admin crean una corrección (nueva marcación).
"""

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import get_client_ip
from personal.permissions import EsRRHHoAdmin, PuedeOperarKiosco

from .models import Marcacion
from .serializers import (
    CorreccionInputSerializer,
    MarcacionInputSerializer,
    MarcacionSerializer,
    SyncBatchSerializer,
)
from .services import (
    MarcacionDuplicada,
    QR_MAX_AGE_SEGUNDOS,
    TokenQRInvalido,
    TokenQRVencido,
    corregir_marcacion,
    generar_token_qr,
    registrar_marcacion,
    sincronizar_lote,
)


class QRKioscoView(APIView):
    """GET /api/marcacion/qr/?sede_id=<id> -> token QR firmado (45 s)."""

    permission_classes = [PuedeOperarKiosco]

    def get(self, request, *args, **kwargs):
        sede_id = request.query_params.get("sede_id")
        if not sede_id:
            raise ValidationError({"sede_id": "Parámetro requerido."})
        token = generar_token_qr(int(sede_id))
        return Response(
            {
                "token_qr": token,
                "sede_id": int(sede_id),
                "expira_en_segundos": QR_MAX_AGE_SEGUNDOS,
            }
        )


class MarcacionCreateView(APIView):
    """POST /api/marcacion/ -> registra una marcación del empleado autenticado.

    Sin permisos propios: hereda los globales (IsAuthenticated + EsSoloLectura),
    de modo que el AUDITOR no puede marcar (POST -> 403).
    """

    def post(self, request, *args, **kwargs):
        empleado = getattr(request.user, "empleado", None)
        if empleado is None:
            raise PermissionDenied(
                "El usuario autenticado no tiene un perfil de empleado."
            )

        entrada = MarcacionInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        try:
            marcacion = registrar_marcacion(
                empleado=empleado,
                token_qr=datos["token_qr"],
                tipo=datos["tipo"],
                latitud=datos["latitud"],
                longitud=datos["longitud"],
                ip_origen=get_client_ip(request),
            )
        except (TokenQRVencido, TokenQRInvalido) as exc:
            # Token vencido o inválido -> 400 con mensaje claro.
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        except MarcacionDuplicada as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_409_CONFLICT
            )

        return Response(
            MarcacionSerializer(marcacion).data, status=status.HTTP_201_CREATED
        )


class SyncOfflineView(APIView):
    """POST /api/marcacion/sync/ -> sincroniza un LOTE de marcaciones offline.

    Sin permisos propios: hereda los globales (IsAuthenticated + EsSoloLectura),
    de modo que el AUDITOR no puede sincronizar (POST -> 403).
    """

    def post(self, request, *args, **kwargs):
        empleado = getattr(request.user, "empleado", None)
        if empleado is None:
            raise PermissionDenied(
                "El usuario autenticado no tiene un perfil de empleado."
            )

        entrada = SyncBatchSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        resultados = sincronizar_lote(
            empleado=empleado,
            items=entrada.validated_data["marcaciones"],
            ip_origen=get_client_ip(request),
        )
        return Response({"resultados": resultados}, status=status.HTTP_200_OK)


class CorreccionView(APIView):
    """POST /api/marcacion/<uuid>/corregir/ -> nueva marcación que corrige a otra."""

    permission_classes = [EsRRHHoAdmin]

    def post(self, request, pk, *args, **kwargs):
        original = get_object_or_404(Marcacion, pk=pk)

        entrada = CorreccionInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        correccion = corregir_marcacion(
            original=original,
            tipo=datos["tipo"],
            latitud=datos["latitud"],
            longitud=datos["longitud"],
            actor_id=str(request.user.pk),
            actor_rol=request.user.rol,
            ip_origen=get_client_ip(request),
            motivo=datos.get("motivo", ""),
        )
        return Response(
            MarcacionSerializer(correccion).data, status=status.HTTP_201_CREATED
        )
