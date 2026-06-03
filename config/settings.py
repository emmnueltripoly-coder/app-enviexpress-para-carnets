"""
Django settings for config project.

Sistema de control de asistencia (BASC + Ley 1581 de Colombia).

Las credenciales y secretos se leen de variables de entorno (.env) mediante
python-dotenv. NUNCA se commitean secretos en este archivo.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga variables desde el archivo .env (si existe) a os.environ.
load_dotenv(BASE_DIR / ".env")


# --------------------------------------------------------------------------
# Seguridad
# --------------------------------------------------------------------------
# SECURITY WARNING: la SECRET_KEY se lee del entorno; nunca debe estar en el código.
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no está definida. Copie .env.example a .env y configúrela."
    )

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]


# --------------------------------------------------------------------------
# Aplicaciones
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    # Apps del proyecto
    "common",
    "auditoria",
    "organizacion",
    "personal",
    "marcacion",
    "turnos",
    "novedades",
    "reportes",
]

# Modelo de usuario personalizado (Hito 1). DEBE definirse antes de la primera
# migración del proyecto; por eso se recrea la BD de desarrollo desde cero.
AUTH_USER_MODEL = "personal.Usuario"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------
# Base de datos: PostgreSQL OBLIGATORIO (BASC exige triggers reales; NO SQLite)
# --------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "asistencia_db"),
        "USER": os.environ.get("DB_USER", "asistencia_user"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}


# --------------------------------------------------------------------------
# Validación de contraseñas
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# --------------------------------------------------------------------------
# Internacionalización / Zona horaria
# --------------------------------------------------------------------------
LANGUAGE_CODE = "es-co"

# Colombia es UTC-5 sin horario de verano. Guardamos SIEMPRE en UTC (USE_TZ=True)
# y presentamos en la zona local de Bogotá. Trazabilidad temporal confiable (BASC).
TIME_ZONE = "America/Bogota"

USE_I18N = True

USE_TZ = True


# --------------------------------------------------------------------------
# Archivos estáticos
# --------------------------------------------------------------------------
STATIC_URL = "static/"

# Almacenamiento PRIVADO para soportes de novedades (datos sensibles de salud,
# Ley 1581). Fuera de cualquier ruta servida públicamente; se entrega solo por
# vista autenticada. NO se define MEDIA_URL para estos archivos.
PRIVATE_MEDIA_ROOT = os.environ.get(
    "PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")
)
# Tamaño máximo de un soporte (bytes) y tipos MIME permitidos.
SOPORTE_MAX_BYTES = int(os.environ.get("SOPORTE_MAX_BYTES", 10 * 1024 * 1024))
SOPORTE_MIME_PERMITIDOS = (
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
)

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Email (notificación de novedades a RRHH)
# --------------------------------------------------------------------------
# Backend configurable; en desarrollo, consola. En tests, pytest-django/Django
# usan automáticamente el backend en memoria (locmem) con mail.outbox.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "no-responder@enviexpresslogistica.com"
)
# Destinatarios de RRHH (de entorno, NO fijos en código).
NOVEDADES_EMAILS = [
    correo.strip()
    for correo in os.environ.get(
        "NOVEDADES_EMAILS",
        "yulieth.alvarez@enviexpresslogistica.com,"
        "gloria.arias@enviexpresslogistica.com",
    ).split(",")
    if correo.strip()
]


# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # Por defecto TODO endpoint exige autenticación (IsAuthenticated) y, además,
    # bloquea cualquier escritura del rol AUDITOR de forma GLOBAL (EsSoloLectura).
    # login/refresh sobreescriben esto con AllowAny.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "personal.permissions.EsSoloLectura",
    ),
}


# --------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt)
# --------------------------------------------------------------------------
# Access corto (se usa en cada request) + refresh largo (renueva el access).
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# --------------------------------------------------------------------------
# django-unfold — Tema del panel administrativo (Hito 7)
# --------------------------------------------------------------------------
UNFOLD = {
    "SITE_TITLE": "Control de Asistencia",
    "SITE_HEADER": "Control de Asistencia — Enviexpress Logística",
    "SITE_URL": "/",
    "SITE_ICON": None,
    "COLORS": {
        "primary": {
            "50": "240 249 255",
            "100": "224 242 254",
            "200": "186 230 253",
            "300": "125 211 252",
            "400": "56 189 248",
            "500": "14 165 233",
            "600": "2 132 199",
            "700": "3 105 161",
            "800": "7 89 133",
            "900": "12 74 110",
            "950": "8 47 73",
        },
    },
    "DASHBOARD_CALLBACK": "config.admin_dashboard.dashboard_callback",
}
