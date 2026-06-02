"""Rutas API de autenticación e identidad (Hito 2)."""

from django.urls import path

from .api import LoginView, MeView, RefreshView

app_name = "personal"

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/refresh/", RefreshView.as_view(), name="refresh"),
    path("me/", MeView.as_view(), name="me"),
]
