"""Utilidades compartidas."""


def get_client_ip(request):
    """Devuelve la IP de origen de la request.

    Respeta X-Forwarded-For (primer valor) cuando la app está detrás de un
    proxy/balanceador; de lo contrario usa REMOTE_ADDR. Se usa para el sello
    ``ip_origen`` de auditoría (trazabilidad BASC).
    """
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
