"""
Tests del Hito 2 (Autenticación y permisos) — corren contra PostgreSQL real.

Verifican:
  (a) Login con credenciales correctas devuelve access + refresh.
  (b) Login con credenciales incorrectas falla (401).
  (c) El login exitoso queda registrado en audit_log.
  (d) Un AUDITOR puede hacer GET pero recibe 403 al intentar POST/PUT/DELETE.
  (e) Un endpoint protegido rechaza peticiones sin token (401).
"""

import pytest
from rest_framework.response import Response
from rest_framework.test import (
    APIClient,
    APIRequestFactory,
    force_authenticate,
)
from rest_framework.views import APIView

from datetime import date

from auditoria.models import AuditLog
from organizacion.models import Empresa, Sede
from personal.models import Empleado, Usuario


# --- Vista de prueba para validar el bloqueo GLOBAL de escritura del AUDITOR.
# Usa los permisos por defecto del proyecto (IsAuthenticated + EsSoloLectura),
# por lo que demuestra que la protección aplica sin declararla en la vista.
class _VistaDemo(APIView):
    def get(self, request):
        return Response({"ok": True})

    def post(self, request):
        return Response({"ok": True})

    def put(self, request):
        return Response({"ok": True})

    def delete(self, request):
        return Response({"ok": True})


def _crear_usuario(username="jperez", password="ClaveSegura123", rol=Usuario.Rol.EMPLEADO):
    return Usuario.objects.create_user(username=username, password=password, rol=rol)


@pytest.mark.django_db
def test_login_credenciales_correctas_devuelve_tokens():
    """(a)"""
    _crear_usuario()
    client = APIClient()

    resp = client.post(
        "/api/auth/login/",
        {"username": "jperez", "password": "ClaveSegura123"},
        format="json",
    )

    assert resp.status_code == 200
    assert "access" in resp.data
    assert "refresh" in resp.data


@pytest.mark.django_db
def test_login_por_documento_identidad():
    """(a complemento) el login también acepta documento_identidad."""
    usuario = _crear_usuario(username="cc.maria", rol=Usuario.Rol.EMPLEADO)
    empresa = Empresa.objects.create(nombre="Enviexpress", nit="900999888-1")
    sede = Sede.objects.create(
        empresa=empresa,
        nombre="Sede Bogotá",
        ciudad=Sede.Ciudad.BOGOTA,
        direccion="Cra 7 # 1-10",
        latitud="4.711000",
        longitud="-74.072100",
    )
    Empleado.objects.create(
        usuario=usuario,
        documento_identidad="52123456",
        nombres="María",
        apellidos="Gómez",
        sede=sede,
        cargo="Analista",
        fecha_ingreso=date(2026, 2, 1),
    )

    resp = APIClient().post(
        "/api/auth/login/",
        {"documento_identidad": "52123456", "password": "ClaveSegura123"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data


@pytest.mark.django_db
def test_login_credenciales_incorrectas_falla():
    """(b)"""
    _crear_usuario()
    client = APIClient()

    resp = client.post(
        "/api/auth/login/",
        {"username": "jperez", "password": "claveIncorrecta"},
        format="json",
    )

    assert resp.status_code == 401
    assert "access" not in resp.data


@pytest.mark.django_db
def test_login_exitoso_queda_en_audit_log():
    """(c)"""
    usuario = _crear_usuario(rol=Usuario.Rol.RRHH)
    client = APIClient()

    assert AuditLog.objects.filter(accion=AuditLog.Accion.LOGIN).count() == 0

    resp = client.post(
        "/api/auth/login/",
        {"username": "jperez", "password": "ClaveSegura123"},
        format="json",
    )
    assert resp.status_code == 200

    logs = AuditLog.objects.filter(accion=AuditLog.Accion.LOGIN)
    assert logs.count() == 1
    log = logs.get()
    assert log.entidad == "Usuario"
    assert log.entidad_id == str(usuario.pk)
    assert log.actor_rol == Usuario.Rol.RRHH
    assert log.metadata["username"] == "jperez"


@pytest.mark.django_db
def test_login_fallido_no_registra_auditoria():
    """(b/c complemento) un login fallido NO crea entrada LOGIN en audit_log."""
    _crear_usuario()
    APIClient().post(
        "/api/auth/login/",
        {"username": "jperez", "password": "mala"},
        format="json",
    )
    assert AuditLog.objects.filter(accion=AuditLog.Accion.LOGIN).count() == 0


@pytest.mark.django_db
def test_auditor_solo_lectura_get_ok_escritura_403():
    """(d) AUDITOR: GET permitido; POST/PUT/DELETE -> 403 (bloqueo global)."""
    auditor = _crear_usuario(username="auditor1", rol=Usuario.Rol.AUDITOR)
    factory = APIRequestFactory()
    vista = _VistaDemo.as_view()

    # GET permitido.
    req_get = factory.get("/demo/")
    force_authenticate(req_get, user=auditor)
    assert vista(req_get).status_code == 200

    # Escrituras bloqueadas.
    for metodo in ("post", "put", "delete"):
        req = getattr(factory, metodo)("/demo/")
        force_authenticate(req, user=auditor)
        assert vista(req).status_code == 403, f"{metodo} debería dar 403 para AUDITOR"


@pytest.mark.django_db
def test_rol_no_auditor_si_puede_escribir():
    """(d complemento) un rol distinto de AUDITOR sí puede escribir."""
    empleado = _crear_usuario(username="emp1", rol=Usuario.Rol.EMPLEADO)
    factory = APIRequestFactory()
    vista = _VistaDemo.as_view()

    req = factory.post("/demo/")
    force_authenticate(req, user=empleado)
    assert vista(req).status_code == 200


@pytest.mark.django_db
def test_endpoint_protegido_sin_token_rechaza():
    """(e) /api/me sin token -> 401."""
    resp = APIClient().get("/api/me/")
    assert resp.status_code == 401


@pytest.mark.django_db
def test_me_con_token_devuelve_rol():
    """(complemento) /api/me con token devuelve datos y rol del usuario."""
    _crear_usuario(username="auditor2", rol=Usuario.Rol.AUDITOR)
    client = APIClient()
    tokens = client.post(
        "/api/auth/login/",
        {"username": "auditor2", "password": "ClaveSegura123"},
        format="json",
    ).data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    resp = client.get("/api/me/")
    assert resp.status_code == 200
    assert resp.data["username"] == "auditor2"
    assert resp.data["rol"] == Usuario.Rol.AUDITOR
