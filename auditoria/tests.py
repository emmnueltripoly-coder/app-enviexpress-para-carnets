"""
Tests del Hito 0 — corren contra PostgreSQL real (NO SQLite).

Verifican que audit_log es append-only:
  (a) AuditService.registrar() inserta correctamente.
  (b) Un UPDATE directo por SQL sobre audit_log es rechazado por el trigger.
  (c) Un DELETE directo por SQL sobre audit_log es rechazado por el trigger.

Las pruebas (b) y (c) envuelven la sentencia que falla en un bloque
``transaction.atomic()`` (savepoint). Así, cuando el trigger aborta la
operación, solo se revierte el savepoint y la transacción externa del test
sigue siendo utilizable para el rollback final de pytest-django.
"""

import pytest
from django.db import Error, connection, transaction

from auditoria.models import AuditLog
from auditoria.services import AuditService


@pytest.mark.django_db
def test_registrar_inserta_auditoria():
    """(a) registrar() crea un AuditLog persistido con los datos dados."""
    log = AuditService.registrar(
        accion=AuditLog.Accion.LOGIN,
        entidad="Usuario",
        actor_id="42",
        actor_rol="ADMIN",
        entidad_id="42",
        metadata={"navegador": "Firefox", "exito": True},
        ip_origen="190.0.0.1",
    )

    assert AuditLog.objects.count() == 1

    guardado = AuditLog.objects.get(pk=log.pk)
    assert guardado.accion == AuditLog.Accion.LOGIN
    assert guardado.entidad == "Usuario"
    assert guardado.actor_id == "42"
    assert guardado.actor_rol == "ADMIN"
    assert guardado.entidad_id == "42"
    assert guardado.metadata == {"navegador": "Firefox", "exito": True}
    assert guardado.ip_origen == "190.0.0.1"
    # created_at se fija automáticamente (trazabilidad temporal, UTC).
    assert guardado.created_at is not None


@pytest.mark.django_db
def test_update_directo_es_rechazado_por_trigger():
    """(b) Un UPDATE directo en BD sobre audit_log debe abortar por el trigger."""
    log = AuditService.registrar(
        accion=AuditLog.Accion.MARCACION,
        entidad="Marcacion",
        entidad_id="1",
    )

    with pytest.raises(Error):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE audit_log SET accion = %s WHERE id = %s",
                    [AuditLog.Accion.LOGIN, str(log.pk)],
                )

    # El registro permanece intacto: la acción no cambió.
    assert AuditLog.objects.get(pk=log.pk).accion == AuditLog.Accion.MARCACION


@pytest.mark.django_db
def test_delete_directo_es_rechazado_por_trigger():
    """(c) Un DELETE directo en BD sobre audit_log debe abortar por el trigger."""
    log = AuditService.registrar(
        accion=AuditLog.Accion.EXPORTACION_DATOS,
        entidad="Reporte",
        entidad_id="7",
    )

    with pytest.raises(Error):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM audit_log WHERE id = %s",
                    [str(log.pk)],
                )

    # El registro sigue existiendo: no se pudo borrar.
    assert AuditLog.objects.filter(pk=log.pk).exists()
