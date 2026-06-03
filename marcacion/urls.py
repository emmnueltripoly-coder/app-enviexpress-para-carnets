"""Rutas API de marcación (Hito 3)."""

from django.urls import path

from .api import CorreccionView, MarcacionCreateView, QRKioscoView

app_name = "marcacion"

urlpatterns = [
    path("", MarcacionCreateView.as_view(), name="crear"),
    path("qr/", QRKioscoView.as_view(), name="qr"),
    path("<uuid:pk>/corregir/", CorreccionView.as_view(), name="corregir"),
]
