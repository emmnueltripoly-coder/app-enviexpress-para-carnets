"""Rutas API de reportes y exportación (Hito 8)."""

from django.urls import path

from .api import (
    HabeasDataEmpleadoView,
    HabeasDataMeView,
    ReporteAsistenciaView,
    ReporteExcepcionesView,
    ReporteHorasView,
    ReporteNovedadesView,
)

app_name = "reportes"

urlpatterns = [
    path("asistencia/", ReporteAsistenciaView.as_view(), name="asistencia"),
    path("horas/", ReporteHorasView.as_view(), name="horas"),
    path("novedades/", ReporteNovedadesView.as_view(), name="novedades"),
    path("excepciones/", ReporteExcepcionesView.as_view(), name="excepciones"),
    path("habeas-data/me/", HabeasDataMeView.as_view(), name="habeas-data-me"),
    path(
        "habeas-data/<int:empleado_id>/",
        HabeasDataEmpleadoView.as_view(),
        name="habeas-data-empleado",
    ),
]
