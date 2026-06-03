"""Rutas API del Hito 5."""

from django.urls import path

from .api import (
    AsignarTurnoView,
    ParametrosLaboralesView,
    RecalcularJornadasView,
    ResumenesView,
)

app_name = "turnos"

urlpatterns = [
    path("asignar/", AsignarTurnoView.as_view(), name="asignar"),
    path("parametros/", ParametrosLaboralesView.as_view(), name="parametros"),
    path("recalcular/", RecalcularJornadasView.as_view(), name="recalcular"),
    path("resumenes/", ResumenesView.as_view(), name="resumenes"),
]
