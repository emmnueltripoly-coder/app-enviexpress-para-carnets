"""
Tests del Hito 6 (Novedades) — corren contra PostgreSQL real.

Cubren: (a) crear novedad PENDIENTE; (b) email a RRHH sin exponer el soporte;
(c) soporte válido/ inválido; (d) archivo no accesible sin auth/permiso (403);
(e) acceso autorizado al soporte queda en audit_log; (f) aprobar/rechazar por
supervisor/RRHH auditado; (g) el dueño no aprueba lo suyo; (h) auditor 403.
"""

from datetime import date

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from auditoria.models import AuditLog
from novedades.models import Novedad, SoporteNovedad
from organizacion.models import Empresa, Sede
from personal.models import Empleado, Usuario

PDF_BYTES = b"%PDF-1.4 contenido de incapacidad medica"


@pytest.fixture(autouse=True)
def _private_media(settings, tmp_path):
    # Almacenamiento privado aislado por test.
    settings.PRIVATE_MEDIA_ROOT = str(tmp_path / "priv")


@pytest.fixture
def empresa():
    return Empresa.objects.create(nombre="Enviexpress", nit="900123456-7")


def _sede(empresa, nombre, ciudad):
    return Sede.objects.create(
        empresa=empresa,
        nombre=nombre,
        ciudad=ciudad,
        direccion="Calle 1",
        latitud="6.24",
        longitud="-75.58",
    )


def _empleado(sede, *, username, documento, rol=Usuario.Rol.EMPLEADO):
    usuario = Usuario.objects.create_user(
        username=username, password="ClaveSegura123", rol=rol
    )
    return Empleado.objects.create(
        usuario=usuario,
        documento_identidad=documento,
        nombres="Nom",
        apellidos="Ape",
        sede=sede,
        cargo="Cargo",
        fecha_ingreso=date(2026, 1, 1),
    )


def _client(usuario):
    c = APIClient()
    c.force_authenticate(user=usuario)
    return c


def _crear_novedad(client):
    return client.post(
        "/api/novedades/",
        {
            "tipo": Novedad.Tipo.INCAPACIDAD,
            "descripcion": "Diagnóstico confidencial del médico tratante.",
            "fecha_inicio": "2026-06-01",
            "fecha_fin": "2026-06-03",
        },
        format="json",
    )


def _subir_soporte(client, novedad_id, *, nombre="inc.pdf", contenido=PDF_BYTES, mime="application/pdf"):
    archivo = SimpleUploadedFile(nombre, contenido, content_type=mime)
    return client.post(
        f"/api/novedades/{novedad_id}/soporte/", {"archivo": archivo}, format="multipart"
    )


# --------------------------------------------------------------------------
# (a) Crear novedad -> PENDIENTE
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_empleado_crea_novedad_pendiente(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")

    resp = _crear_novedad(_client(emp.usuario))

    assert resp.status_code == 201, resp.data
    assert resp.data["estado"] == Novedad.Estado.PENDIENTE
    assert Novedad.objects.count() == 1
    assert AuditLog.objects.filter(accion=AuditLog.Accion.NOVEDAD_CREADA).count() == 1


# --------------------------------------------------------------------------
# (b) Email a RRHH sin exponer datos sensibles
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_crear_novedad_envia_email_sin_exponer_soporte(
    empresa, settings, django_capture_on_commit_callbacks
):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")

    with django_capture_on_commit_callbacks(execute=True):
        resp = _crear_novedad(_client(emp.usuario))
    assert resp.status_code == 201

    assert len(mail.outbox) == 1
    correo = mail.outbox[0]
    assert set(correo.to) == set(settings.NOVEDADES_EMAILS)
    # Resumen presente, pero NADA del contenido sensible.
    assert "Incapacidad" in correo.subject
    assert "Diagnóstico confidencial" not in correo.body  # descripción no se expone
    assert "Ley 1581" in correo.body  # aviso de protección de datos


# --------------------------------------------------------------------------
# (c) Soporte válido / inválido
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_soporte_valido_e_invalido(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")
    client = _client(emp.usuario)
    novedad = Novedad.objects.create(
        empleado=emp, tipo=Novedad.Tipo.INCAPACIDAD,
        descripcion="x", fecha_inicio=date(2026, 6, 1),
    )

    ok = _subir_soporte(client, novedad.pk, nombre="inc.pdf", mime="application/pdf")
    assert ok.status_code == 201, ok.data
    assert SoporteNovedad.objects.count() == 1

    malo = _subir_soporte(
        client, novedad.pk, nombre="virus.txt", contenido=b"texto", mime="text/plain"
    )
    assert malo.status_code == 400
    assert SoporteNovedad.objects.count() == 1  # no se creó el inválido


# --------------------------------------------------------------------------
# (d) Archivo no accesible sin autenticación / sin permiso
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_soporte_no_accesible_sin_permiso(empresa):
    sede1 = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    sede2 = _sede(empresa, "Cali", Sede.Ciudad.CALI)
    dueno = _empleado(sede1, username="cc.dueno", documento="100")
    ajeno = _empleado(sede2, username="cc.ajeno", documento="200")

    novedad = Novedad.objects.create(
        empleado=dueno, tipo=Novedad.Tipo.INCAPACIDAD,
        descripcion="x", fecha_inicio=date(2026, 6, 1),
    )
    soporte_id = _subir_soporte(_client(dueno.usuario), novedad.pk).data["id"]
    url = f"/api/novedades/soporte/{soporte_id}/descargar/"

    # Sin autenticación -> 401.
    assert APIClient().get(url).status_code == 401
    # Otro empleado (no dueño, no gestor) -> 403.
    assert _client(ajeno.usuario).get(url).status_code == 403


# --------------------------------------------------------------------------
# (e) Acceso autorizado al soporte queda en audit_log
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_acceso_autorizado_a_soporte_se_audita(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    dueno = _empleado(sede, username="cc.dueno", documento="100")
    novedad = Novedad.objects.create(
        empleado=dueno, tipo=Novedad.Tipo.INCAPACIDAD,
        descripcion="x", fecha_inicio=date(2026, 6, 1),
    )
    soporte_id = _subir_soporte(_client(dueno.usuario), novedad.pk).data["id"]

    resp = _client(dueno.usuario).get(
        f"/api/novedades/soporte/{soporte_id}/descargar/"
    )
    assert resp.status_code == 200
    assert b"".join(resp.streaming_content) == PDF_BYTES

    logs = AuditLog.objects.filter(accion=AuditLog.Accion.SOPORTE_ACCEDIDO)
    assert logs.count() == 1
    log = logs.get()
    assert log.entidad == "SoporteNovedad"
    assert log.actor_id == str(dueno.usuario_id)
    assert log.metadata["modo"] == "descarga"


# --------------------------------------------------------------------------
# (f) Supervisor / RRHH aprueban y rechazan, auditado
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_supervisor_y_rrhh_gestionan_estado(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")
    supervisor = _empleado(
        sede, username="cc.sup", documento="200", rol=Usuario.Rol.SUPERVISOR
    )
    rrhh = Usuario.objects.create_user(username="rrhh", password="x", rol=Usuario.Rol.RRHH)

    n1 = Novedad.objects.create(
        empleado=emp, tipo=Novedad.Tipo.PERMISO, descripcion="x", fecha_inicio=date(2026, 6, 1)
    )
    n2 = Novedad.objects.create(
        empleado=emp, tipo=Novedad.Tipo.PERMISO, descripcion="y", fecha_inicio=date(2026, 6, 2)
    )

    # Supervisor de la sede aprueba n1.
    r1 = _client(supervisor.usuario).post(
        f"/api/novedades/{n1.pk}/aprobar/", {"comentario": "ok"}, format="json"
    )
    assert r1.status_code == 200
    n1.refresh_from_db()
    assert n1.estado == Novedad.Estado.APROBADA

    # RRHH rechaza n2.
    r2 = _client(rrhh).post(
        f"/api/novedades/{n2.pk}/rechazar/", {"comentario": "incompleto"}, format="json"
    )
    assert r2.status_code == 200
    n2.refresh_from_db()
    assert n2.estado == Novedad.Estado.RECHAZADA

    assert AuditLog.objects.filter(accion=AuditLog.Accion.NOVEDAD_APROBADA).count() == 1
    assert AuditLog.objects.filter(accion=AuditLog.Accion.NOVEDAD_RECHAZADA).count() == 1


# --------------------------------------------------------------------------
# (g) El dueño no aprueba sus propias novedades
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_empleado_no_aprueba_sus_propias_novedades(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")
    novedad = Novedad.objects.create(
        empleado=emp, tipo=Novedad.Tipo.PERMISO, descripcion="x", fecha_inicio=date(2026, 6, 1)
    )

    resp = _client(emp.usuario).post(
        f"/api/novedades/{novedad.pk}/aprobar/", {}, format="json"
    )
    assert resp.status_code == 403
    novedad.refresh_from_db()
    assert novedad.estado == Novedad.Estado.PENDIENTE


# --------------------------------------------------------------------------
# (h) Auditor 403 al aprobar (y no puede descargar contenido)
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_auditor_no_puede_aprobar_ni_descargar(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp = _empleado(sede, username="cc.emp", documento="100")
    auditor = Usuario.objects.create_user(username="auditor", password="x", rol=Usuario.Rol.AUDITOR)
    novedad = Novedad.objects.create(
        empleado=emp, tipo=Novedad.Tipo.INCAPACIDAD, descripcion="x", fecha_inicio=date(2026, 6, 1)
    )
    soporte_id = _subir_soporte(_client(emp.usuario), novedad.pk).data["id"]

    # Aprobar -> 403 (permiso global del Hito 2 bloquea escritura del auditor).
    r1 = _client(auditor).post(f"/api/novedades/{novedad.pk}/aprobar/", {}, format="json")
    assert r1.status_code == 403

    # Descargar contenido sensible -> 403 (auditor no accede al archivo).
    r2 = _client(auditor).get(f"/api/novedades/soporte/{soporte_id}/descargar/")
    assert r2.status_code == 403

    # Pero SÍ puede ver metadatos, y ese acceso queda registrado.
    r3 = _client(auditor).get(f"/api/novedades/soporte/{soporte_id}/")
    assert r3.status_code == 200
    assert (
        AuditLog.objects.filter(
            accion=AuditLog.Accion.SOPORTE_ACCEDIDO, actor_id=str(auditor.pk)
        ).count()
        == 1
    )
