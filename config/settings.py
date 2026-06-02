"""
Django settings for config project.

Sistema de control de asistencia (BASC + Ley 1581 de Colombia).

Las credenciales y secretos se leen de variables de entorno (.env) mediante
python-dotenv. NUNCA se commitean secretos en este archivo.
"""

import os
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

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Django REST Framework
# --------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}
