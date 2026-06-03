"""
Vistas API del Hito 5.

Permisos:
- Asignar turnos y editar parámetros: solo RRHH/Admin (EsRRHHoAdmin). El AUDITOR
  queda fuera (no está en el conjunto) y, además, el permiso global del Hito 2
  bloquea sus escrituras.
- Recalcular: RRHH/Admin.
- Consultar resúmenes: el empleado ve lo suyo; RRHH/Admin puede consultar a otros.
"""

from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from common.utils import get_client_ip
from personal.models import Empleado, Usuario
from personal.permissions import EsRRHHoAdmin

from .models import ResumenJornada, Turno
from .serializers import (
    AsignarTurnoSerializer,
    ParametrosInputSerializer,
    ParametrosLaboralesSerializer,
    RecalcularSerializer,
    ResumenJornadaSerializer,
)
from .services import (
    asignar_turno,
    calcular_jornadas,
    crear_version_parametros,
)


class AsignarTurnoView(APIView):
    """POST /api/turnos/asignar/ -> crea una asignación de turno (RRHH/Admin)."""

    permission_classes = [EsRRHHoAdmin]

    def post(self, request, *args, **kwargs):
        entrada = AsignarTurnoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data

        empleado = get_object_or_404(Empleado, pk=datos["empleado_id"])
        turno = get_object_or_404(Turno, pk=datos["turno_id"])

        asignacion = asignar_turno(
            empleado=empleado,
            turno=turno,
            fecha_inicio=datos["fecha_inicio"],
            fecha_fin=datos.get("fecha_fin"),
            actor_id=str(request.user.pk),
            actor_rol=request.user.rol,
            ip_origen=get_client_ip(request),
        )
        return Response(
            {
                "id": asignacion.pk,
                "empleado_id": empleado.pk,
                "turno_id": turno.pk,
                "fecha_inicio": asignacion.fecha_inicio,
                "fecha_fin": asignacion.fecha_fin,
            },
            status=status.HTTP_201_CREATED,
        )


class ParametrosLaboralesView(APIView):
    """GET vigentes (autenticado) / POST nueva versión (RRHH/Admin)."""

    def get_permissions(self):
        if self.request.method == "POST":
            return [EsRRHHoAdmin()]
        return super().get_permissions()

    def post(self, request, *args, **kwargs):
        entrada = ParametrosInputSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        parametros = crear_version_parametros(
            actor_id=str(request.user.pk),
            actor_rol=request.user.rol,
            ip_origen=get_client_ip(request),
            **entrada.validated_data,
        )
        return Response(
            ParametrosLaboralesSerializer(parametros).data,
            status=status.HTTP_201_CREATED,
        )


class RecalcularJornadasView(APIView):
    """POST /api/turnos/recalcular/ -> recalcula los resúmenes (RRHH/Admin)."""

    permission_classes = [EsRRHHoAdmin]

    def post(self, request, *args, **kwargs):
        entrada = RecalcularSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        if datos["fecha_inicio"] > datos["fecha_fin"]:
            raise ValidationError("fecha_inicio no puede ser mayor que fecha_fin.")

        empleado = get_object_or_404(Empleado, pk=datos["empleado_id"])
        resumenes = calcular_jornadas(
            empleado, datos["fecha_inicio"], datos["fecha_fin"]
        )
        return Response(
            {"resumenes": ResumenJornadaSerializer(resumenes, many=True).data}
        )


class ResumenesView(APIView):
    """GET /api/turnos/resumenes/ -> resúmenes de jornada.

    El empleado ve los suyos. RRHH/Admin puede pasar ?empleado_id=<id>.
    """

    def get(self, request, *args, **kwargs):
        usuario = request.user
        empleado_id = request.query_params.get("empleado_id")

        if empleado_id and usuario.rol in {Usuario.Rol.RRHH, Usuario.Rol.ADMIN}:
            empleado = get_object_or_404(Empleado, pk=empleado_id)
        else:
            empleado = getattr(usuario, "empleado", None)
            if empleado is None:
                raise PermissionDenied(
                    "El usuario autenticado no tiene un perfil de empleado."
                )

        resumenes = ResumenJornada.objects.filter(empleado=empleado)
        return Response(
            {"resumenes": ResumenJornadaSerializer(resumenes, many=True).data}
        )
