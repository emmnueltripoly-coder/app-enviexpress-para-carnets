"""
Django settings — Control de asistencia Enviexpress (BASC + Ley 1581).

ENTORNOS:
  Desarrollo  — DEBUG=True en .env; usa DB_* vars y FileSystemStorage local.
  Producción  — DEBUG=False; usa DATABASE_URL (Supabase) y puede usar
                Supabase Storage (S3) si se proveen credenciales.

SECRETOS: NUNCA en este archivo. Todo via variables de entorno (.env en dev,
          panel de Render en prod). Ver .env.example para la lista completa.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Carga .env si existe (desarrollo). En producción (Render) las vars ya están
# inyectadas por la plataforma; load_dotenv no hace nada si no hay .env.
load_dotenv(BASE_DIR / ".env")


# ==========================================================================
# SEGURIDAD BÁSICA
# ==========================================================================
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no está definida. Copie .env.example a .env y configúrela."
    )

DEBUG = os.environ.get("DEBUG", "False").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]


# ==========================================================================
# APLICACIONES
# ==========================================================================
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
    "corsheaders",
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

AUTH_USER_MODEL = "personal.Usuario"


# ==========================================================================
# MIDDLEWARE — orden importante: WhiteNoise justo después de Security;
#              CorsMiddleware antes de CommonMiddleware.
# ==========================================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",       # archivos estáticos en prod
    "corsheaders.middleware.CorsMiddleware",            # CORS antes de CommonMiddleware
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


# ==========================================================================
# BASE DE DATOS
# PostgreSQL OBLIGATORIO (BASC exige triggers reales; NO SQLite).
#
# DATABASE_URL tiene prioridad (Render + Supabase usan este formato).
# Si no está definido se usan las variables DB_* individuales (desarrollo).
# ==========================================================================
import dj_database_url  # noqa: E402 — importación local para mantener legibilidad

_DATABASE_URL = os.environ.get("DATABASE_URL")
_CONN_MAX_AGE = int(os.environ.get("CONN_MAX_AGE", "0"))
# Nota: con el connection pooler de Supabase (puerto 6543, modo transaction)
# CONN_MAX_AGE debe ser 0. Para conexión directa (puerto 5432) puede ser 60.

if _DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=_DATABASE_URL,
            conn_max_age=_CONN_MAX_AGE,
            conn_health_checks=True,
        )
    }
else:
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


# ==========================================================================
# VALIDACIÓN DE CONTRASEÑAS
# ==========================================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ==========================================================================
# INTERNACIONALIZACIÓN / ZONA HORARIA
# Colombia = UTC-5 sin horario de verano. USE_TZ=True: todo en UTC en BD,
# presentación en America/Bogota. Trazabilidad temporal confiable (BASC).
# ==========================================================================
LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True


# ==========================================================================
# ARCHIVOS ESTÁTICOS
# WhiteNoise sirve los estáticos en producción (admin Unfold + DRF browsable).
# STATIC_ROOT es donde collectstatic deposita los archivos.
# ==========================================================================
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ==========================================================================
# ALMACENAMIENTO PRIVADO — soportes de novedades (datos sensibles, Ley 1581)
# Fuera de MEDIA_URL; se sirve solo por SoporteDescargarView (autenticada).
# En producción auto-cambia a Supabase S3 si se definen las credenciales.
# ==========================================================================
PRIVATE_MEDIA_ROOT = os.environ.get(
    "PRIVATE_MEDIA_ROOT", str(BASE_DIR / "private_media")
)
SOPORTE_MAX_BYTES = int(os.environ.get("SOPORTE_MAX_BYTES", 10 * 1024 * 1024))
SOPORTE_MIME_PERMITIDOS = (
    "image/jpeg",
    "image/png",
    "image/jpg",
    "application/pdf",
)

# Supabase Storage (S3-compatible) — solo se activa si la clave está definida.
# Si no está, PrivateMediaStorage cae al almacenamiento local (desarrollo).
SUPABASE_S3_ACCESS_KEY = os.environ.get("SUPABASE_S3_ACCESS_KEY", "")
SUPABASE_S3_SECRET_KEY = os.environ.get("SUPABASE_S3_SECRET_KEY", "")
SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "novedades-soportes")
SUPABASE_S3_ENDPOINT_URL = os.environ.get("SUPABASE_S3_ENDPOINT_URL", "")
SUPABASE_S3_REGION = os.environ.get("SUPABASE_S3_REGION", "us-east-1")


# ==========================================================================
# DEFAULT PK
# ==========================================================================
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ==========================================================================
# EMAIL — notificación de novedades a RRHH
# ==========================================================================
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "no-responder@enviexpresslogistica.com"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in ("1", "true", "yes")

# Destinatarios RRHH (de entorno, nunca fijos en código).
NOVEDADES_EMAILS = [
    correo.strip()
    for correo in os.environ.get(
        "NOVEDADES_EMAILS",
        "yulieth.alvarez@enviexpresslogistica.com,"
        "gloria.arias@enviexpresslogistica.com",
    ).split(",")
    if correo.strip()
]


# ==========================================================================
# CORS — solo orígenes explícitos (app móvil web + panel futuro)
# Para la app React Native nativa (iOS/Android) CORS no aplica; solo
# para builds web / futuros frontends.
# ==========================================================================
CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8081",
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = False  # JWT en header, no en cookie → no hace falta


# ==========================================================================
# DJANGO REST FRAMEWORK
# ==========================================================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    # IsAuthenticated + EsSoloLectura → AUDITOR bloqueado globalmente de escritura.
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
        "personal.permissions.EsSoloLectura",
    ),
}


# ==========================================================================
# JWT (djangorestframework-simplejwt)
# ==========================================================================
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ==========================================================================
# django-unfold — Tema del panel administrativo
# ==========================================================================
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


# ==========================================================================
# SEGURIDAD DE PRODUCCIÓN
# Solo activa cuando DEBUG=False. Con DEBUG=True el servidor de desarrollo
# no necesita estas cabeceras (y algunas romperían el flujo local).
# ==========================================================================
if not DEBUG:
    # Render termina TLS en su load balancer y reenvía X-Forwarded-Proto.
    # Con este header, Django sabe que la conexión original fue HTTPS.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Redirige HTTP → HTTPS a nivel de Django (backup al redirect de Render).
    SECURE_SSL_REDIRECT = True

    # Cookies seguras: solo se envían por HTTPS.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: le dice al navegador que use HTTPS durante 1 año.
    # Después de verificar que el sitio funciona, se puede activar preload.
    SECURE_HSTS_SECONDS = 31_536_000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Protección adicional contra sniffing y clickjacking.
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
