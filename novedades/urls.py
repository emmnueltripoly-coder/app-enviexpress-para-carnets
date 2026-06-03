"""Rutas API de novedades (Hito 6)."""

from django.urls import path

from .api import (
    AprobarNovedadView,
    NovedadesView,
    RechazarNovedadView,
    SoporteDescargarView,
    SoporteMetadatosView,
    SoporteUploadView,
)

app_name = "novedades"

urlpatterns = [
    path("", NovedadesView.as_view(), name="lista"),
    path("<uuid:pk>/soporte/", SoporteUploadView.as_view(), name="soporte-subir"),
    path("<uuid:pk>/aprobar/", AprobarNovedadView.as_view(), name="aprobar"),
    path("<uuid:pk>/rechazar/", RechazarNovedadView.as_view(), name="rechazar"),
    path("soporte/<int:pk>/", SoporteMetadatosView.as_view(), name="soporte-metadatos"),
    path(
        "soporte/<int:pk>/descargar/",
        SoporteDescargarView.as_view(),
        name="soporte-descargar",
    ),
]
