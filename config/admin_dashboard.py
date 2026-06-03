"""Callback del dashboard de unfold (Hito 7)."""

from django.utils import timezone


def dashboard_callback(request, context):
    """Inyecta indicadores simples en el contexto del dashboard de unfold."""
    from marcacion.models import Marcacion
    from novedades.models import Novedad
    from personal.models import Empleado

    hoy = timezone.localdate()

    marcaciones_hoy = Marcacion.objects.filter(
        timestamp_servidor__date=hoy
    ).count()
    fuera_sede_hoy = Marcacion.objects.filter(
        timestamp_servidor__date=hoy, fuera_de_sede=True
    ).count()
    revisar_offline = Marcacion.objects.filter(revisar_offline=True).count()
    novedades_pendientes = Novedad.objects.filter(
        estado=Novedad.Estado.PENDIENTE, activo=True
    ).count()
    empleados_activos = Empleado.objects.filter(activo=True).count()

    context["dashboard_cards"] = [
        {
            "label": "Marcaciones hoy",
            "value": marcaciones_hoy,
            "icon": "check_circle",
        },
        {
            "label": "Fuera de geocerca (hoy)",
            "value": fuera_sede_hoy,
            "icon": "location_off",
        },
        {
            "label": "Marcaciones offline a revisar",
            "value": revisar_offline,
            "icon": "wifi_off",
        },
        {
            "label": "Novedades pendientes",
            "value": novedades_pendientes,
            "icon": "pending_actions",
        },
        {
            "label": "Empleados activos",
            "value": empleados_activos,
            "icon": "group",
        },
    ]
    return context
