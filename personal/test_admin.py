"""
Tests del Hito 7 — permisos del panel de administración.

Cubren: (a) empleado sin is_staff no puede acceder; (b) AUDITOR en modo solo
lectura (has_add/change/delete=False, sin acciones); (c) queryset de Supervisor
filtrado por sede; (d) RRHH aprueba novedad desde el admin y queda auditado;
(e) las acciones de aprobar/rechazar no aparecen para el AUDITOR.
"""

from datetime import date

import pytest
from django.contrib import admin as django_admin
from django.test import RequestFactory

from auditoria.models import AuditLog
from marcacion.admin import MarcacionAdmin
from novedades.admin import NovedadAdmin
from novedades.models import Novedad
from organizacion.models import Empresa, Sede
from personal.admin import EmpleadoAdmin
from personal.models import Empleado, Usuario


# ---------------------------------------------------------------------------
# Fixtures reutilizables
# ---------------------------------------------------------------------------

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


def _usuario(*, username, rol, is_staff=True):
    u = Usuario.objects.create_user(
        username=username, password="ClaveSegura123", rol=rol
    )
    u.is_staff = is_staff
    u.save()
    return u


def _empleado(sede, usuario):
    return Empleado.objects.create(
        usuario=usuario,
        documento_identidad=f"DOC-{usuario.username}",
        nombres="Nom",
        apellidos="Ape",
        sede=sede,
        cargo="Cargo",
        fecha_ingreso=date(2026, 1, 1),
    )


def _fake_request(user):
    """RequestFactory crea requests sin pasar por middleware; útil para pruebas de unidad de admin."""
    factory = RequestFactory()
    request = factory.get("/admin/")
    request.user = user
    return request


# ---------------------------------------------------------------------------
# (a) Empleado sin is_staff no puede acceder al admin
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_empleado_sin_is_staff_no_accede_al_admin(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    empleado_usr = _usuario(username="emp1", rol=Usuario.Rol.EMPLEADO, is_staff=False)
    _empleado(sede, empleado_usr)

    from django.test import Client
    c = Client()
    c.force_login(empleado_usr)
    resp = c.get("/admin/")
    # Sin is_staff Django redirige al login (302) o retorna 403.
    assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# (b) AUDITOR: has_add / has_change / has_delete devuelven False
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_auditor_solo_lectura_en_admin(empresa):
    from marcacion.models import Marcacion

    auditor = _usuario(username="auditor1", rol=Usuario.Rol.AUDITOR)
    request = _fake_request(auditor)

    marcacion_admin = MarcacionAdmin(Marcacion, django_admin.site)

    assert marcacion_admin.has_add_permission(request) is False
    assert marcacion_admin.has_change_permission(request) is False
    assert marcacion_admin.has_delete_permission(request) is False


# ---------------------------------------------------------------------------
# (c) Queryset del Supervisor filtrado por su propia sede
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_supervisor_queryset_filtrado_por_sede(empresa):
    sede1 = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    sede2 = _sede(empresa, "Cali", Sede.Ciudad.CALI)

    sup_usr = _usuario(username="sup1", rol=Usuario.Rol.SUPERVISOR)
    _empleado(sede1, sup_usr)  # el supervisor pertenece a sede1

    # Empleado en sede1 y otro en sede2.
    emp1_usr = _usuario(username="emp1", rol=Usuario.Rol.EMPLEADO, is_staff=False)
    emp2_usr = _usuario(username="emp2", rol=Usuario.Rol.EMPLEADO, is_staff=False)
    _empleado(sede1, emp1_usr)
    _empleado(sede2, emp2_usr)

    from django.test import RequestFactory
    request = _fake_request(sup_usr)

    from personal.models import Empleado as EmpModel
    emp_admin = EmpleadoAdmin(EmpModel, django_admin.site)
    qs = emp_admin.get_queryset(request)

    documentos = set(qs.values_list("documento_identidad", flat=True))
    # Solo debe ver a emp1 (de sede1) y al supervisor mismo, no a emp2.
    assert f"DOC-{emp1_usr.username}" in documentos
    assert f"DOC-{emp2_usr.username}" not in documentos


# ---------------------------------------------------------------------------
# (d) RRHH aprueba novedad desde admin → queda en audit_log
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_rrhh_aprueba_novedad_desde_admin_y_audita(empresa):
    sede = _sede(empresa, "Medellín", Sede.Ciudad.MEDELLIN)
    emp_usr = _usuario(username="emp1", rol=Usuario.Rol.EMPLEADO, is_staff=False)
    emp = _empleado(sede, emp_usr)
    rrhh_usr = _usuario(username="rrhh1", rol=Usuario.Rol.RRHH)

    novedad = Novedad.objects.create(
        empleado=emp,
        tipo=Novedad.Tipo.PERMISO,
        descripcion="Solicitud de permiso",
        fecha_inicio=date(2026, 6, 1),
    )
    assert novedad.estado == Novedad.Estado.PENDIENTE

    request = _fake_request(rrhh_usr)
    request.META["REMOTE_ADDR"] = "127.0.0.1"

    novedad_admin = NovedadAdmin(Novedad, django_admin.site)
    # Simula la selección de la acción de aprobación en masa.
    from novedades.admin import _aprobar_novedades
    _aprobar_novedades(novedad_admin, request, Novedad.objects.filter(pk=novedad.pk))

    novedad.refresh_from_db()
    assert novedad.estado == Novedad.Estado.APROBADA
    assert AuditLog.objects.filter(accion=AuditLog.Accion.NOVEDAD_APROBADA).count() == 1


# ---------------------------------------------------------------------------
# (e) El AUDITOR no recibe acciones de escritura en NovedadAdmin
# ---------------------------------------------------------------------------
@pytest.mark.django_db
def test_auditor_no_recibe_acciones_de_novedades(empresa):
    from novedades.admin import _aprobar_novedades, _rechazar_novedades

    auditor = _usuario(username="auditor2", rol=Usuario.Rol.AUDITOR)
    request = _fake_request(auditor)

    novedad_admin = NovedadAdmin(Novedad, django_admin.site)
    acciones = novedad_admin.get_actions(request)

    # El mixin AuditorReadOnlyMixin devuelve {} para AUDITOR: sin acciones de escritura.
    assert _aprobar_novedades.__name__ not in acciones
    assert _rechazar_novedades.__name__ not in acciones
