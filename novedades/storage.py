"""
Almacenamiento PRIVADO para soportes de novedades.

Los soportes pueden contener datos sensibles de salud (incapacidades médicas),
protegidos por la Ley 1581. Por eso:
- Se guardan en PRIVATE_MEDIA_ROOT, fuera de cualquier ruta servida públicamente.
- base_url se deja en None: el FileField NO expone una URL pública; el archivo
  solo se entrega a través de una vista autenticada que verifica permisos.

La ubicación se lee de settings en tiempo de ejecución (property) para permitir
override_settings en tests.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)


private_storage = PrivateMediaStorage()
