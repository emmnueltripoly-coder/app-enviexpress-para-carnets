"""
Tests del Hito 1 (Identidad) — corren contra PostgreSQL real.

Verifican:
  (a) Se crea un Empleado con su Usuario y rol.
  (b) Se registra un ConsentimientoHabeasData y queda en audit_log.
  (c) desactivar() pone activo=False SIN borrar el registro.
  (d) Un documento_identidad duplicado es rechazado por la BD.
"""

from datetime import date

import pytest
from django.db import IntegrityError

from auditoria.models import AuditLog
from organizacion.models import Empresa, Sede
from personal.models import ConsentimientoHabeasData, Empleado, Usuario
from personal.services import (
    crear_empleado_con_usuario,
    registrar_consentimiento,
)


@pytest.fixture
def sede(db):
    empresa = Empresa.objects.create(nombre="Enviexpress", nit="900123456-7")
    return Sede.objects.create(
        empresa=empresa,
        nombre="Sede Medellín",
        ciudad=Sede.Ciudad.MEDELLIN,
        direccion="Calle 10 # 20-30",
        latitud="6.244203",
        longitud="-75.581215",
        radio_metros=120,
    )


def _crear_empleado(sede, *, username="cc.alopez", documento="1037612345"):
    return crear_empleado_con_usuario(
        username=username,
        password="ClaveSegura123",
        rol=Usuario.Rol.EMPLEADO,
        documento_identidad=documento,
        nombres="Ana",
        apellidos="López",
        sede=sede,
        cargo="Auxiliar logística",
        fecha_ingreso=date(2026, 1, 15),
    )


@pytest.mark.django_db
def test_crear_empleado_con_usuario_y_rol(sede):
    """(a) Empleado + Usuario con rol, y queda rastro EMPLEADO_CREADO en audit_log."""
    empleado = _crear_empleado(sede)

    assert Empleado.objects.count() == 1
    assert empleado.usuario.rol == Usuario.Rol.EMPLEADO
    assert empleado.usuario.username == "cc.alopez"
    assert empleado.documento_identidad == "1037612345"
    assert empleado.sede == sede
    # La contraseña se guarda hasheada, nunca en claro.
    assert empleado.usuario.password != "ClaveSegura123"
    assert empleado.usuario.check_password("ClaveSegura123")

    # Auditoría de la creación.
    log = AuditLog.objects.get(accion=AuditLog.Accion.EMPLEADO_CREADO)
    assert log.entidad == "Empleado"
    assert log.entidad_id == str(empleado.pk)


@pytest.mark.django_db
def test_registrar_consentimiento_queda_en_audit_log(sede):
    """(b) ConsentimientoHabeasData persistido + entrada en audit_log."""
    empleado = _crear_empleado(sede)

    consentimiento = registrar_consentimiento(
        empleado=empleado,
        version_politica="2026.1",
        texto_politica="Autorizo el tratamiento de mis datos personales...",
        aceptado=True,
        ip_aceptacion="190.85.10.20",
    )

    assert ConsentimientoHabeasData.objects.count() == 1
    assert consentimiento.aceptado is True
    assert consentimiento.version_politica == "2026.1"

    log = AuditLog.objects.get(accion=AuditLog.Accion.CONSENTIMIENTO_REGISTRADO)
    assert log.entidad == "ConsentimientoHabeasData"
    assert log.entidad_id == str(consentimiento.pk)
    assert log.metadata["version_politica"] == "2026.1"
    assert log.ip_origen == "190.85.10.20"


@pytest.mark.django_db
def test_desactivar_hace_soft_delete(sede):
    """(c) desactivar() pone activo=False sin borrar el registro."""
    empleado = _crear_empleado(sede)
    pk = empleado.pk

    empleado.desactivar()

    empleado.refresh_from_db()
    assert empleado.activo is False
    # El registro sigue existiendo físicamente (no hubo borrado).
    assert Empleado.objects.filter(pk=pk).exists()
    # Y el manager 'activos' ya no lo devuelve.
    assert not Empleado.activos.filter(pk=pk).exists()


@pytest.mark.django_db
def test_documento_identidad_duplicado_es_rechazado(sede):
    """(d) Un documento_identidad duplicado viola la unicidad y es rechazado."""
    _crear_empleado(sede, username="cc.alopez", documento="1037612345")

    with pytest.raises(IntegrityError):
        _crear_empleado(sede, username="cc.otro", documento="1037612345")
