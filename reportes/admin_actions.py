"""
Acciones de exportación para el panel admin (Unfold, Hito 8).

Cada acción opera sobre el queryset YA filtrado del changelist (que respeta los
filtros de Unfold: sede, fechas, fuera_de_sede, etc.) y devuelve la descarga.
La auditoría (EXPORTACION_DATOS) la hace ``services.exportar``, así que también
las exportaciones desde el admin quedan trazadas.

El rol AUDITOR no recibe NINGUNA acción (lo bloquea ``AuditorReadOnlyMixin``);
sus reportes de lectura los obtiene por la API, donde su acceso también se audita.
"""

from django.contrib import messages
from django.utils import timezone


def _meta_admin(request):
    return {
        "Origen": "Panel administrativo",
        "Generado por": request.user.get_username(),
        "Rol": request.user.get_rol_display(),
        "Generado": timezone.localtime().strftime("%Y-%m-%d %H:%M"),
    }


# --- Asistencia (sobre Marcacion) -----------------------------------------
def exportar_asistencia_excel(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_asistencia(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="xlsx", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_asistencia",
        accion_meta={"reporte": "asistencia", "origen": "admin"},
    )
    return services.http_response(result)


exportar_asistencia_excel.short_description = "Exportar asistencia seleccionada (Excel)"


def exportar_asistencia_pdf(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_asistencia(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="pdf", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_asistencia",
        accion_meta={"reporte": "asistencia", "origen": "admin"},
    )
    return services.http_response(result)


exportar_asistencia_pdf.short_description = "Exportar asistencia seleccionada (PDF)"


def exportar_excepciones_excel(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_excepciones(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="xlsx", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_excepciones",
        accion_meta={"reporte": "excepciones", "origen": "admin"},
    )
    return services.http_response(result)


exportar_excepciones_excel.short_description = "Exportar excepciones (BASC) de la selección (Excel)"


# --- Horas (sobre ResumenJornada) -----------------------------------------
def exportar_horas_excel(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_horas(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="xlsx", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_horas",
        accion_meta={"reporte": "horas", "origen": "admin"},
    )
    return services.http_response(result)


exportar_horas_excel.short_description = "Exportar horas seleccionadas (Excel)"


def exportar_horas_pdf(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_horas(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="pdf", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_horas",
        accion_meta={"reporte": "horas", "origen": "admin"},
    )
    return services.http_response(result)


exportar_horas_pdf.short_description = "Exportar horas seleccionadas (PDF)"


# --- Novedades (sobre Novedad) --------------------------------------------
def exportar_novedades_excel(modeladmin, request, queryset):
    from . import services

    reporte = services.recolectar_novedades(queryset, meta=_meta_admin(request))
    result = services.exportar(
        reporte=reporte, formato="xlsx", actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base="reporte_novedades",
        accion_meta={"reporte": "novedades", "origen": "admin"},
    )
    return services.http_response(result)


exportar_novedades_excel.short_description = "Exportar novedades seleccionadas (Excel)"


# --- Habeas Data individual (sobre Empleado) ------------------------------
def _exportar_habeas_data(request, queryset, formato):
    from . import services

    if queryset.count() != 1:
        return None  # señal: selección inválida (la maneja el wrapper)
    empleado = queryset.first()
    reporte = services.recolectar_habeas_data(empleado)
    result = services.exportar(
        reporte=reporte, formato=formato, actor=request.user,
        ip_origen=request.META.get("REMOTE_ADDR"),
        nombre_base=f"habeas_data_{empleado.documento_identidad}",
        accion_meta={
            "reporte": "habeas_data",
            "empleado_id": empleado.pk,
            "titular_documento": empleado.documento_identidad,
            "origen": "admin",
        },
        entidad="Empleado",
        entidad_id=empleado.pk,
    )
    return services.http_response(result)


def exportar_habeas_data_excel(modeladmin, request, queryset):
    from . import services  # noqa: F401  (mantiene simetría de imports)

    respuesta = _exportar_habeas_data(request, queryset, "xlsx")
    if respuesta is None:
        modeladmin.message_user(
            request,
            "Seleccione exactamente un empleado para exportar su Habeas Data.",
            messages.WARNING,
        )
    return respuesta


exportar_habeas_data_excel.short_description = "Exportar Habeas Data del empleado (Excel)"


def exportar_habeas_data_pdf(modeladmin, request, queryset):
    respuesta = _exportar_habeas_data(request, queryset, "pdf")
    if respuesta is None:
        modeladmin.message_user(
            request,
            "Seleccione exactamente un empleado para exportar su Habeas Data.",
            messages.WARNING,
        )
    return respuesta


exportar_habeas_data_pdf.short_description = "Exportar Habeas Data del empleado (PDF)"
