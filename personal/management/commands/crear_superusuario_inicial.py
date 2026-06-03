"""
Comando: python manage.py crear_superusuario_inicial

Crea el superusuario inicial del sistema de forma segura desde variables de
entorno. Idempotente: si el usuario ya existe, informa y no falla.

Variables de entorno requeridas:
  DJANGO_SUPERUSER_USERNAME  — nombre de usuario (ej: admin)
  DJANGO_SUPERUSER_PASSWORD  — contraseña segura
  DJANGO_SUPERUSER_EMAIL     — email (opcional; recomendado)

El usuario creado tiene:
  - is_staff = True    → puede acceder al panel admin
  - is_superuser = True → todos los permisos
  - rol = ADMIN        → rol de negocio del sistema

Uso en el build command de Render (después de migrate):
  python manage.py crear_superusuario_inicial
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from personal.models import Usuario


class Command(BaseCommand):
    help = "Crea el superusuario inicial desde variables de entorno (idempotente)."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()

        if not username:
            raise CommandError(
                "DJANGO_SUPERUSER_USERNAME no está definida. "
                "Configúrela en el panel de variables de entorno de Render."
            )
        if not password:
            raise CommandError(
                "DJANGO_SUPERUSER_PASSWORD no está definida. "
                "Configúrela en el panel de variables de entorno de Render."
            )

        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"El usuario '{username}' ya existe. No se realizó ningún cambio."
                )
            )
            return

        User.objects.create_superuser(
            username=username,
            password=password,
            email=email,
            rol=Usuario.Rol.ADMIN,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Superusuario '{username}' creado con rol ADMIN. "
                "Cambie la contraseña después del primer inicio de sesión."
            )
        )
