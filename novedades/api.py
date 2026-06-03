"""
Vistas API de novedades (Hito 6).

Permisos (además del global del Hito 2: auditor no escribe):
- Crear novedad / adjuntar soporte: el empleado dueño.
- Aprobar/rechazar: RRHH/Admin o Supervisor de la sede del empleado; NUNCA el
  propio dueño (no autoaprobación).
- Listar: el empleado ve lo suyo; supervisor su sede; RRHH/Admin/Auditor todo.
- Descargar soporte (contenido sensible): dueño o gestor; el AUDITOR no.
  Cada acceso (descarga o metadatos) se registra en audit_log.
"""

from django.http import FileResponse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import get_client_ip
from personal.models import Empleado, Usuario

from .models import Novedad, SoporteNovedad
from .permissions import (
    es_dueno,
    puede_gestionar,
    puede_ver_contenido_soporte,
    puede_ver_metadatos_soporte,
)
from .serializers import (
    CambioEstadoSerializer,
    NovedadInputSerializer,
    NovedadSerializer,
    SoporteMetadatosSerializer,
    SoporteUploadSerializer,
)
from .services import (
    adjuntar_soporte,
    cambiar_estado,
    crear_novedad,
    registrar_acceso_soporte,
)


def _empleado_de(request):
    empleado = getattr(request.user, "empleado", None)
    if empleado is None:
        raise PermissionDenied(
            "El usuario autenticado no tiene un perfil de empleado."
        )
    return empleado


class NovedadesView(APIView):
    """GET lista (según rol) / POST crea (empleado dueño)."""

    def get(self, request, *args, **kwargs):
        usuario = request.user
        qs = Novedad.objects.select_related("empleado")
        if usuario.rol in {Usuario.Rol.RRHH, Usuario.Rol.ADMIN, Usuario.Rol.AUDITOR}:
            pass  # ven todas
        elif usuario.rol == Usuario.Rol.SUPERVISOR:
            empleado = getattr(usuario, "empleado", None)
            sede_id = empleado.sede_id if empleado else None
            qs = qs.filter(empleado__sede_id=sede_id)
        else:
            empleado = _empleado_de(request)
            qs = qs.filter(empleado=empleado)
        return Response(NovedadSerializer(qs, many=True).data)

    def post(self, request, *args, **kwargs):
        empleado = _empleado_de(request)
        entrada = NovedadInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        novedad = crear_novedad(
            empleado=empleado,
            ip_origen=get_client_ip(request),
            **entrada.validated_data,
        )
        return Response(
            NovedadSerializer(novedad).data, status=status.HTTP_201_CREATED
        )


class SoporteUploadView(APIView):
    """POST /api/novedades/<id>/soporte/ -> adjunta un soporte (dueño o gestor)."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk, *args, **kwargs):
        novedad = get_object_or_404(Novedad, pk=pk)
        if not (es_dueno(request.user, novedad) or puede_gestionar(request.user, novedad)):
            raise PermissionDenied("No autorizado para adjuntar a esta novedad.")

        entrada = SoporteUploadSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        soporte = adjuntar_soporte(
            novedad=novedad,
            archivo=entrada.validated_data["archivo"],
            usuario=request.user,
        )
        return Response(
            SoporteMetadatosSerializer(soporte).data, status=status.HTTP_201_CREATED
        )


class SoporteMetadatosView(APIView):
    """GET metadatos del soporte (incluye auditor). Registra el acceso."""

    def get(self, request, pk, *args, **kwargs):
        soporte = get_object_or_404(
            SoporteNovedad.objects.select_related("novedad__empleado"), pk=pk
        )
        if not puede_ver_metadatos_soporte(request.user, soporte.novedad):
            raise PermissionDenied("No autorizado para ver este soporte.")
        registrar_acceso_soporte(
            soporte=soporte, usuario=request.user, modo="metadatos",
            ip_origen=get_client_ip(request),
        )
        return Response(SoporteMetadatosSerializer(soporte).data)


class SoporteDescargarView(APIView):
    """GET el CONTENIDO del soporte (dato sensible). Solo dueño/gestor; auditor NO.

    Cada descarga se registra en audit_log.
    """

    def get(self, request, pk, *args, **kwargs):
        soporte = get_object_or_404(
            SoporteNovedad.objects.select_related("novedad__empleado"), pk=pk
        )
        if not puede_ver_contenido_soporte(request.user, soporte.novedad):
            raise PermissionDenied(
                "No autorizado para descargar este soporte."
            )
        registrar_acceso_soporte(
            soporte=soporte, usuario=request.user, modo="descarga",
            ip_origen=get_client_ip(request),
        )
        archivo = soporte.archivo.open("rb")
        respuesta = FileResponse(
            archivo,
            content_type=soporte.tipo_mime or "application/octet-stream",
            as_attachment=True,
            filename=soporte.nombre_original,
        )
        return respuesta


class _CambioEstadoBase(APIView):
    nuevo_estado = None

    def post(self, request, pk, *args, **kwargs):
        novedad = get_object_or_404(
            Novedad.objects.select_related("empleado"), pk=pk
        )
        # Solo gestores; y NUNCA autoaprobación/autorrechazo por el dueño.
        if es_dueno(request.user, novedad) or not puede_gestionar(request.user, novedad):
            raise PermissionDenied(
                "No autorizado para gestionar el estado de esta novedad."
            )
        entrada = CambioEstadoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        novedad = cambiar_estado(
            novedad=novedad,
            nuevo_estado=self.nuevo_estado,
            usuario=request.user,
            comentario=entrada.validated_data.get("comentario", ""),
            ip_origen=get_client_ip(request),
        )
        return Response(NovedadSerializer(novedad).data)


class AprobarNovedadView(_CambioEstadoBase):
    nuevo_estado = Novedad.Estado.APROBADA


class RechazarNovedadView(_CambioEstadoBase):
    nuevo_estado = Novedad.Estado.RECHAZADA
