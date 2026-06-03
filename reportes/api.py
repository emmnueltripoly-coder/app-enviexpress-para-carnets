"""
Vistas API de reportes y exportación (Hito 8).

Todos los endpoints son de SOLO LECTURA (GET) sobre datos existentes; no tocan
marcaciones ni audit_log salvo para registrar la propia exportación.

Permisos:
- Reportes agregados: RRHH/Admin/Supervisor/Auditor (``PuedeGenerarReportes``).
  El Supervisor queda acotado a su propia sede. Un empleado normal -> 403.
- Habeas Data ``/me/``: cualquier usuario autenticado con perfil de empleado
  puede exportar LO SUYO.
- Habeas Data ``/<empleado_id>/``: solo el propio titular, RRHH o Admin
  (``puede_exportar_habeas_data``); de lo contrario 403.

Formato: ?formato=xlsx (por defecto) o ?formato=pdf.
Rango:   ?desde=YYYY-MM-DD&hasta=YYYY-MM-DD (por defecto, mes en curso).
Sede:    ?sede=<id> (ignorado/forzado para Supervisor).
"""

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from common.utils import get_client_ip
from marcacion.models import Marcacion
from novedades.models import Novedad
from organizacion.models import Sede
from personal.models import Empleado, Usuario
from turnos.models import ResumenJornada

from . import services
from .permissions import PuedeGenerarReportes, puede_exportar_habeas_data

FORMATOS_VALIDOS = {"xlsx", "pdf"}


# --------------------------------------------------------------------------
# Helpers de parámetros
# --------------------------------------------------------------------------
def _formato(request) -> str:
    formato = request.query_params.get("formato", "xlsx").lower()
    if formato not in FORMATOS_VALIDOS:
        raise ValidationError({"formato": "Use 'xlsx' o 'pdf'."})
    return formato


def _fecha(request, nombre, por_defecto):
    raw = request.query_params.get(nombre)
    if not raw:
        return por_defecto
    valor = parse_date(raw)
    if valor is None:
        raise ValidationError({nombre: "Fecha inválida; use el formato YYYY-MM-DD."})
    return valor


def _periodo(request):
    hoy = timezone.localdate()
    desde = _fecha(request, "desde", hoy.replace(day=1))
    hasta = _fecha(request, "hasta", hoy)
    if desde > hasta:
        raise ValidationError({"rango": "'desde' no puede ser posterior a 'hasta'."})
    return desde, hasta


def _sede_id(request):
    """Sede solicitada; para el Supervisor se fuerza a la suya."""
    if request.user.rol == Usuario.Rol.SUPERVISOR:
        empleado = getattr(request.user, "empleado", None)
        return empleado.sede_id if empleado else None
    return request.query_params.get("sede") or None


def _nombre_sede(sede_id):
    if not sede_id:
        return "Todas"
    sede = Sede.objects.filter(pk=sede_id).first()
    return sede.nombre if sede else str(sede_id)


def _meta(desde, hasta, sede_id, actor):
    return {
        "Periodo": f"{desde} a {hasta}",
        "Sede": _nombre_sede(sede_id),
        "Generado por": actor.get_username(),
        "Rol": actor.get_rol_display(),
        "Generado": timezone.localtime().strftime("%Y-%m-%d %H:%M"),
    }


# --------------------------------------------------------------------------
# Reportes agregados
# --------------------------------------------------------------------------
class _ReporteAgregadoView(APIView):
    permission_classes = [IsAuthenticated, PuedeGenerarReportes]


class ReporteAsistenciaView(_ReporteAgregadoView):
    def get(self, request):
        desde, hasta = _periodo(request)
        formato = _formato(request)
        sede_id = _sede_id(request)
        qs = Marcacion.objects.filter(
            minuto_marcacion__date__gte=desde, minuto_marcacion__date__lte=hasta
        )
        if sede_id:
            qs = qs.filter(sede_id=sede_id)
        reporte = services.recolectar_asistencia(
            qs, meta=_meta(desde, hasta, sede_id, request.user)
        )
        result = services.exportar(
            reporte=reporte,
            formato=formato,
            actor=request.user,
            ip_origen=get_client_ip(request),
            nombre_base=f"reporte_asistencia_{desde}_{hasta}",
            accion_meta={
                "reporte": "asistencia",
                "desde": str(desde),
                "hasta": str(hasta),
                "sede_id": sede_id,
            },
        )
        return services.http_response(result)


class ReporteHorasView(_ReporteAgregadoView):
    def get(self, request):
        desde, hasta = _periodo(request)
        formato = _formato(request)
        sede_id = _sede_id(request)
        qs = ResumenJornada.objects.filter(fecha__gte=desde, fecha__lte=hasta)
        if sede_id:
            qs = qs.filter(empleado__sede_id=sede_id)
        reporte = services.recolectar_horas(
            qs, meta=_meta(desde, hasta, sede_id, request.user)
        )
        result = services.exportar(
            reporte=reporte,
            formato=formato,
            actor=request.user,
            ip_origen=get_client_ip(request),
            nombre_base=f"reporte_horas_{desde}_{hasta}",
            accion_meta={
                "reporte": "horas",
                "desde": str(desde),
                "hasta": str(hasta),
                "sede_id": sede_id,
            },
        )
        return services.http_response(result)


class ReporteNovedadesView(_ReporteAgregadoView):
    def get(self, request):
        desde, hasta = _periodo(request)
        formato = _formato(request)
        sede_id = _sede_id(request)
        qs = Novedad.objects.filter(
            activo=True, fecha_inicio__gte=desde, fecha_inicio__lte=hasta
        )
        if sede_id:
            qs = qs.filter(empleado__sede_id=sede_id)
        reporte = services.recolectar_novedades(
            qs, meta=_meta(desde, hasta, sede_id, request.user)
        )
        result = services.exportar(
            reporte=reporte,
            formato=formato,
            actor=request.user,
            ip_origen=get_client_ip(request),
            nombre_base=f"reporte_novedades_{desde}_{hasta}",
            accion_meta={
                "reporte": "novedades",
                "desde": str(desde),
                "hasta": str(hasta),
                "sede_id": sede_id,
            },
        )
        return services.http_response(result)


class ReporteExcepcionesView(_ReporteAgregadoView):
    def get(self, request):
        desde, hasta = _periodo(request)
        formato = _formato(request)
        sede_id = _sede_id(request)
        qs = Marcacion.objects.filter(
            minuto_marcacion__date__gte=desde, minuto_marcacion__date__lte=hasta
        )
        if sede_id:
            qs = qs.filter(sede_id=sede_id)
        reporte = services.recolectar_excepciones(
            qs, meta=_meta(desde, hasta, sede_id, request.user)
        )
        result = services.exportar(
            reporte=reporte,
            formato=formato,
            actor=request.user,
            ip_origen=get_client_ip(request),
            nombre_base=f"reporte_excepciones_{desde}_{hasta}",
            accion_meta={
                "reporte": "excepciones",
                "desde": str(desde),
                "hasta": str(hasta),
                "sede_id": sede_id,
            },
        )
        return services.http_response(result)


# --------------------------------------------------------------------------
# Exportación individual Habeas Data
# --------------------------------------------------------------------------
def _exportar_habeas_data(request, empleado):
    formato = _formato(request)
    reporte = services.recolectar_habeas_data(empleado)
    result = services.exportar(
        reporte=reporte,
        formato=formato,
        actor=request.user,
        ip_origen=get_client_ip(request),
        nombre_base=f"habeas_data_{empleado.documento_identidad}",
        accion_meta={
            "reporte": "habeas_data",
            "empleado_id": empleado.pk,
            "titular_documento": empleado.documento_identidad,
        },
        entidad="Empleado",
        entidad_id=empleado.pk,
    )
    return services.http_response(result)


class HabeasDataMeView(APIView):
    """El usuario autenticado exporta SUS propios datos personales."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        empleado = getattr(request.user, "empleado", None)
        if empleado is None:
            raise ValidationError(
                "El usuario autenticado no tiene un perfil de empleado asociado."
            )
        return _exportar_habeas_data(request, empleado)


class HabeasDataEmpleadoView(APIView):
    """Exporta el expediente de un empleado dado (titular, RRHH o Admin)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, empleado_id):
        empleado = get_object_or_404(Empleado, pk=empleado_id)
        if not puede_exportar_habeas_data(request.user, empleado):
            raise PermissionDenied(
                "No autorizado para exportar los datos personales de este empleado."
            )
        return _exportar_habeas_data(request, empleado)
