"""
Vista de diagnóstico TEMPORAL para producción.

Permite verificar la configuración de email y de Supabase Storage desde el
navegador (sin necesidad de Shell de pago), porque solo el rol staff puede
acceder. NO expone secretos: de las contraseñas/llaves solo muestra si están
definidas y su longitud, nunca el valor.

Quitar este archivo y su ruta cuando el despliegue esté verificado.
"""

from __future__ import annotations

import traceback

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.utils.html import escape


def _mask(valor: str) -> str:
    """Muestra solo si un secreto está definido y su longitud, nunca el valor."""
    if not valor:
        return "(vacío)"
    return f"(definido, {len(valor)} caracteres)"


@staff_member_required
def diagnostico_email(request):
    lineas = ["<h1>Diagnóstico de Email</h1>", "<h2>Configuración actual</h2>", "<ul>"]
    lineas.append(f"<li>EMAIL_BACKEND: {escape(settings.EMAIL_BACKEND)}</li>")
    lineas.append(f"<li>EMAIL_HOST: {escape(settings.EMAIL_HOST)}</li>")
    lineas.append(f"<li>EMAIL_PORT: {settings.EMAIL_PORT}</li>")
    lineas.append(f"<li>EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}</li>")
    lineas.append(f"<li>EMAIL_HOST_USER: {escape(settings.EMAIL_HOST_USER or '(vacío)')}</li>")
    lineas.append(f"<li>EMAIL_HOST_PASSWORD: {_mask(settings.EMAIL_HOST_PASSWORD)}</li>")
    lineas.append(f"<li>DEFAULT_FROM_EMAIL: {escape(settings.DEFAULT_FROM_EMAIL)}</li>")
    lineas.append(f"<li>NOVEDADES_EMAILS: {escape(', '.join(settings.NOVEDADES_EMAILS) or '(vacío)')}</li>")
    lineas.append("</ul>")

    destinatarios = settings.NOVEDADES_EMAILS or [settings.DEFAULT_FROM_EMAIL]
    lineas.append("<h2>Resultado del envío de prueba</h2>")
    try:
        from django.core.mail import send_mail

        enviados = send_mail(
            "Prueba de diagnóstico — Enviexpress",
            "Si lees esto, el correo SMTP funciona correctamente.",
            settings.DEFAULT_FROM_EMAIL,
            destinatarios,
            fail_silently=False,
        )
        lineas.append(
            f"<p style='color:green'><b>OK</b> — send_mail devolvió {enviados}. "
            f"Revisa la bandeja (y spam) de: {escape(', '.join(destinatarios))}</p>"
        )
    except Exception:  # noqa: BLE001 — queremos ver CUALQUIER error
        lineas.append(
            "<p style='color:red'><b>FALLÓ el envío.</b> Detalle del error:</p>"
            f"<pre style='background:#eee;padding:1em'>{escape(traceback.format_exc())}</pre>"
        )

    return HttpResponse("\n".join(lineas))


@staff_member_required
def diagnostico_storage(request):
    lineas = ["<h1>Diagnóstico de Storage</h1>", "<h2>Configuración actual</h2>", "<ul>"]
    lineas.append(f"<li>SUPABASE_S3_ACCESS_KEY: {_mask(settings.SUPABASE_S3_ACCESS_KEY)}</li>")
    lineas.append(f"<li>SUPABASE_S3_SECRET_KEY: {_mask(settings.SUPABASE_S3_SECRET_KEY)}</li>")
    lineas.append(f"<li>SUPABASE_S3_ENDPOINT_URL: {escape(settings.SUPABASE_S3_ENDPOINT_URL or '(vacío)')}</li>")
    lineas.append(f"<li>SUPABASE_STORAGE_BUCKET: {escape(settings.SUPABASE_STORAGE_BUCKET)}</li>")
    lineas.append(f"<li>SUPABASE_S3_REGION: {escape(settings.SUPABASE_S3_REGION)}</li>")
    lineas.append("</ul>")

    lineas.append("<h2>Prueba de subida/borrado de archivo</h2>")
    try:
        from django.core.files.base import ContentFile

        from novedades.storage import PrivateMediaStorage

        storage = PrivateMediaStorage()
        backend = "Supabase S3" if storage._s3() is not None else "Filesystem local (efímero)"
        lineas.append(f"<p>Backend activo: <b>{escape(backend)}</b></p>")

        nombre = storage.save("diagnostico/prueba.txt", ContentFile(b"prueba enviexpress"))
        existe = storage.exists(nombre)
        storage.delete(nombre)
        lineas.append(
            f"<p style='color:green'><b>OK</b> — archivo guardado como "
            f"'{escape(nombre)}' (existe={existe}) y borrado correctamente.</p>"
        )
    except Exception:  # noqa: BLE001
        lineas.append(
            "<p style='color:red'><b>FALLÓ.</b> Detalle del error:</p>"
            f"<pre style='background:#eee;padding:1em'>{escape(traceback.format_exc())}</pre>"
        )

    return HttpResponse("\n".join(lineas))
