"""
Almacenamiento PRIVADO para soportes de novedades (datos sensibles, Ley 1581).

AUTO-SELECCIÓN DE BACKEND:
- Desarrollo / tests (sin SUPABASE_S3_ACCESS_KEY): FileSystemStorage local en
  PRIVATE_MEDIA_ROOT. La ubicación se lee como propiedad en cada operación para
  que override_settings funcione en los tests (fixture _private_media).
- Producción (SUPABASE_S3_ACCESS_KEY presente): S3Boto3Storage apuntando al
  bucket PRIVADO de Supabase Storage. La instancia boto3 se cachea a nivel de
  clase para no recrear la sesión HTTP en cada request.

REGLA NO NEGOCIABLE (Ley 1581):
  base_url = None → nunca se expone una URL directa. El archivo SOLO se entrega
  a través de SoporteDescargarView, que verifica permisos y registra en audit_log.
"""

import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateMediaStorage(FileSystemStorage):
    """Storage privado con auto-selección S3 / filesystem según entorno.

    Se hereda de FileSystemStorage para que deconstruct() devuelva la misma
    forma que la migración inicial: ("novedades.storage.PrivateMediaStorage", [], {})
    → no se genera ninguna migración nueva al agregar el soporte S3.
    """

    # --- Cache de la instancia S3 (costosa de crear; se reutiliza entre requests) ---
    _s3_instance = None

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(*args, **kwargs)

    # --- Dev / tests: lee PRIVATE_MEDIA_ROOT en cada acceso (override_settings ok) ---
    @property
    def base_location(self):
        return settings.PRIVATE_MEDIA_ROOT

    @property
    def location(self):
        return os.path.abspath(self.base_location)

    # --- Selección de backend en tiempo de ejecución ---
    def _s3(self):
        """Devuelve la instancia S3 si hay credenciales; None en caso contrario."""
        key = getattr(settings, "SUPABASE_S3_ACCESS_KEY", "") or ""
        if not key:
            return None
        if PrivateMediaStorage._s3_instance is None:
            from storages.backends.s3boto3 import S3Boto3Storage
            PrivateMediaStorage._s3_instance = S3Boto3Storage(
                access_key=key,
                secret_key=getattr(settings, "SUPABASE_S3_SECRET_KEY", ""),
                bucket_name=getattr(settings, "SUPABASE_STORAGE_BUCKET", "novedades-soportes"),
                endpoint_url=getattr(settings, "SUPABASE_S3_ENDPOINT_URL", ""),
                region_name=getattr(settings, "SUPABASE_S3_REGION", "us-east-1"),
                default_acl="private",
                # Sin querystring_auth: la URL generada por url() no se expone;
                # el acceso siempre pasa por la vista autenticada de Django.
                querystring_auth=False,
                custom_domain=None,
            )
        return PrivateMediaStorage._s3_instance

    # --- Delegación transparente a S3 o filesystem ---
    def _open(self, name, mode="rb"):
        s3 = self._s3()
        return s3._open(name, mode) if s3 else super()._open(name, mode)

    def _save(self, name, content):
        s3 = self._s3()
        return s3._save(name, content) if s3 else super()._save(name, content)

    def delete(self, name):
        s3 = self._s3()
        if s3:
            s3.delete(name)
        else:
            super().delete(name)

    def exists(self, name):
        s3 = self._s3()
        return s3.exists(name) if s3 else super().exists(name)

    def size(self, name):
        s3 = self._s3()
        return s3.size(name) if s3 else super().size(name)

    def url(self, name):
        s3 = self._s3()
        if s3:
            return s3.url(name)
        # En modo filesystem, base_url=None → NotImplementedError intencionado:
        # el archivo nunca debe exponerse por URL pública directa.
        raise NotImplementedError(
            "Los soportes privados no tienen URL pública. "
            "Usa SoporteDescargarView para servir el archivo de forma autenticada."
        )

    def generate_filename(self, filename):
        s3 = self._s3()
        return s3.generate_filename(filename) if s3 else super().generate_filename(filename)

    def deconstruct(self):
        # Devuelve la misma forma que FileSystemStorage serializa para esta clase,
        # sin argumentos, para que Django no detecte un cambio de migración.
        return ("novedades.storage.PrivateMediaStorage", [], {})


private_storage = PrivateMediaStorage()
