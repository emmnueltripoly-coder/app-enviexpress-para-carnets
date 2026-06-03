"""
Tests del Hito 5 (Turnos y horas extra) — corren contra PostgreSQL real.

Cubren: (a) asignación fija y rotativa; (b) jornada normal; (c) extra diurnas;
(d) franja nocturna (recargo + extra nocturna); (e) festivo; (f) cruce de
medianoche; (g) tardanza; (h) cambio de parámetro -> recálculo + audit_log;
(i) auditor 403 al asignar turno.
"""

from datetime import date, datetime, time
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from auditoria.models import AuditLog
from marcacion.models import Marcacion
from organizacion.models import Empresa, Sede
from personal.models import Empleado, Usuario
from turnos.models import (
    AsignacionTurno,
    DiaFestivo,
    ResumenJornada,
    Turno,
)
from turnos.services import (
    asignar_turno,
    calcular_jornadas,
    crear_version_parametros,
    turno_vigente,
)

LAT = Decimal("6.244203")
LON = Decimal("-75.581215")
DIA = date(2026, 6, 3)  # miércoles (no domingo)


def _sede():
    empresa = Empresa.objects.create(nombre="Enviexpress", nit="900123456-7")
    return Sede.objects.create(
        empresa=empresa,
        nombre="Sede Medellín",
        ciudad=Sede.Ciudad.MEDELLIN,
        direccion="Calle 10",
        latitud=LAT,
        longitud=LON,
    )


def _empleado(sede, *, username="cc.emp", documento="1001"):
    usuario = Usuario.objects.create_user(
        username=username, password="ClaveSegura123", rol=Usuario.Rol.EMPLEADO
    )
    return Empleado.objects.create(
        usuario=usuario,
        documento_identidad=documento,
        nombres="Ana",
        apellidos="López",
        sede=sede,
        cargo="Auxiliar",
        fecha_ingreso=date(2026, 1, 1),
    )


def _turno(nombre, ini, fin, *, cruza=False, sede=None):
    return Turno.objects.create(
        nombre=nombre, hora_inicio=ini, hora_fin=fin, cruza_medianoche=cruza, sede=sede
    )


def _marca(empleado, sede, tipo, dt_local):
    aware = timezone.make_aware(dt_local, timezone.get_current_timezone())
    return Marcacion.objects.create(
        empleado=empleado,
        sede=sede,
        tipo=tipo,
        latitud=LAT,
        longitud=LON,
        fuera_de_sede=False,
        distancia_metros=Decimal("0.00"),
        timestamp_qr=aware,
        timestamp_servidor=aware,
    )


def _jornada(empleado, sede, fecha, h_ini, m_ini, h_fin, m_fin, *, dia_fin=None):
    """Crea ENTRADA/SALIDA para una jornada y devuelve el ResumenJornada."""
    _marca(
        empleado, sede, Marcacion.Tipo.ENTRADA,
        datetime(fecha.year, fecha.month, fecha.day, h_ini, m_ini),
    )
    f2 = dia_fin or fecha
    _marca(
        empleado, sede, Marcacion.Tipo.SALIDA,
        datetime(f2.year, f2.month, f2.day, h_fin, m_fin),
    )
    calcular_jornadas(empleado, fecha, f2)
    return ResumenJornada.objects.get(empleado=empleado, fecha=fecha)


# --------------------------------------------------------------------------
# (a) Asignación fija y rotativa
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_asignacion_fija_y_rotativa():
    sede = _sede()
    fijo = _empleado(sede, username="cc.fijo", documento="100")
    rota = _empleado(sede, username="cc.rota", documento="200")
    t_dia = _turno("Diurno", time(8, 0), time(16, 0))
    t_tarde = _turno("Tarde", time(14, 0), time(22, 0))

    # Fijo: asignación abierta.
    asignar_turno(empleado=fijo, turno=t_dia, fecha_inicio=date(2026, 1, 1))
    # Rotativo: dos semanas con turnos distintos.
    asignar_turno(empleado=rota, turno=t_dia, fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 6, 7))
    asignar_turno(empleado=rota, turno=t_tarde, fecha_inicio=date(2026, 6, 8), fecha_fin=date(2026, 6, 14))

    assert turno_vigente(fijo, date(2026, 6, 3)) == t_dia
    assert turno_vigente(fijo, date(2027, 1, 1)) == t_dia  # abierta: sigue vigente
    assert turno_vigente(rota, date(2026, 6, 3)) == t_dia
    assert turno_vigente(rota, date(2026, 6, 10)) == t_tarde

    # Quedó auditado como TURNO_CAMBIADO.
    assert AuditLog.objects.filter(accion=AuditLog.Accion.TURNO_CAMBIADO).count() == 3
    assert AsignacionTurno.objects.count() == 3


# --------------------------------------------------------------------------
# (b) Jornada normal sin extra
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_jornada_normal_sin_extra():
    sede = _sede()
    emp = _empleado(sede)
    turno = _turno("Diurno", time(8, 0), time(16, 0))
    asignar_turno(empleado=emp, turno=turno, fecha_inicio=date(2026, 1, 1))

    r = _jornada(emp, sede, DIA, 8, 0, 16, 0)

    assert r.horas_ordinarias == Decimal("8.00")
    assert r.horas_extra_diurnas == Decimal("0.00")
    assert r.horas_extra_nocturnas == Decimal("0.00")
    assert r.horas_recargo_nocturno == Decimal("0.00")
    assert r.horas_dominical_festivo == Decimal("0.00")
    assert r.tardanza_minutos == 0
    assert r.salida_temprana_minutos == 0


# --------------------------------------------------------------------------
# (c) Horas extra diurnas
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_horas_extra_diurnas():
    sede = _sede()
    emp = _empleado(sede)
    # 08:00 a 18:00 = 10 h, todo diurno (franja nocturna inicia 21:00).
    r = _jornada(emp, sede, DIA, 8, 0, 18, 0)

    assert r.horas_ordinarias == Decimal("8.00")
    assert r.horas_extra_diurnas == Decimal("2.00")
    assert r.horas_extra_nocturnas == Decimal("0.00")
    assert r.horas_recargo_nocturno == Decimal("0.00")


# --------------------------------------------------------------------------
# (d) Franja nocturna: recargo nocturno + extra nocturna
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_franja_nocturna_recargo_y_extra():
    sede = _sede()
    emp = _empleado(sede)
    # 14:00 a 23:00 = 9 h. Franja nocturna 21:00-06:00, ordinaria 8 h.
    #   14:00-21:00 (7 h) ordinarias diurnas
    #   21:00-22:00 (1 h) ordinaria nocturna -> recargo_nocturno
    #   22:00-23:00 (1 h) extra nocturna
    r = _jornada(emp, sede, DIA, 14, 0, 23, 0)

    assert r.horas_ordinarias == Decimal("7.00")
    assert r.horas_recargo_nocturno == Decimal("1.00")
    assert r.horas_extra_nocturnas == Decimal("1.00")
    assert r.horas_extra_diurnas == Decimal("0.00")
    assert r.horas_dominical_festivo == Decimal("0.00")


# --------------------------------------------------------------------------
# (e) Día festivo
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_dia_festivo():
    sede = _sede()
    emp = _empleado(sede)
    DiaFestivo.objects.create(fecha=DIA, descripcion="Festivo de prueba")

    r = _jornada(emp, sede, DIA, 8, 0, 16, 0)

    assert r.horas_dominical_festivo == Decimal("8.00")
    assert r.horas_ordinarias == Decimal("0.00")


# --------------------------------------------------------------------------
# (f) Turno que cruza medianoche
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_turno_cruza_medianoche():
    sede = _sede()
    emp = _empleado(sede)
    turno = _turno("Noche", time(22, 0), time(6, 0), cruza=True)
    asignar_turno(empleado=emp, turno=turno, fecha_inicio=date(2026, 1, 1))

    # Turno completo: 22:00 del DIA a 06:00 del día siguiente = 8 h, toda nocturna
    # y ordinaria (los minutos tras medianoche son del día 4 pero siguen en franja
    # nocturna). La jornada se atribuye a la fecha de la ENTRADA.
    r = _jornada(emp, sede, DIA, 22, 0, 6, 0, dia_fin=date(2026, 6, 4))

    assert r.fecha == DIA
    assert r.horas_recargo_nocturno == Decimal("8.00")
    assert r.horas_ordinarias == Decimal("0.00")
    assert r.horas_extra_nocturnas == Decimal("0.00")
    assert r.tardanza_minutos == 0
    assert r.salida_temprana_minutos == 0


# --------------------------------------------------------------------------
# (g) Tardanza
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_deteccion_tardanza():
    sede = _sede()
    emp = _empleado(sede)
    turno = _turno("Diurno", time(8, 0), time(16, 0))
    asignar_turno(empleado=emp, turno=turno, fecha_inicio=date(2026, 1, 1))

    r = _jornada(emp, sede, DIA, 8, 25, 16, 0)  # entra 25 min tarde

    assert r.tardanza_minutos == 25
    assert r.salida_temprana_minutos == 0


# --------------------------------------------------------------------------
# (h) Cambiar parámetro -> recálculo usa el nuevo valor + audit_log
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_cambio_parametro_afecta_recalculo_y_audita():
    sede = _sede()
    emp = _empleado(sede)
    # 20:00 a 22:00. Con franja nocturna por defecto (21:00):
    #   20:00-21:00 ordinaria diurna; 21:00-22:00 recargo nocturno.
    r = _jornada(emp, sede, DIA, 20, 0, 22, 0)
    assert r.horas_ordinarias == Decimal("1.00")
    assert r.horas_recargo_nocturno == Decimal("1.00")

    audits_antes = AuditLog.objects.filter(
        accion=AuditLog.Accion.CONFIG_CAMBIADA
    ).count()

    # Nueva versión: la franja nocturna ahora inicia a las 20:00.
    nuevos = crear_version_parametros(
        inicio_jornada_nocturna=time(20, 0),
        fin_jornada_nocturna=time(6, 0),
        horas_jornada_ordinaria_diaria=Decimal("8.00"),
        porcentaje_extra_diurna=Decimal("25.00"),
        porcentaje_extra_nocturna=Decimal("75.00"),
        porcentaje_recargo_nocturno=Decimal("35.00"),
        porcentaje_dominical_festivo=Decimal("75.00"),
        vigente_desde=DIA,
        descripcion="Franja nocturna desde 20:00",
        actor_id="1",
        actor_rol=Usuario.Rol.RRHH,
    )

    # Recalcular: ahora 20:00-22:00 es toda nocturna.
    calcular_jornadas(emp, DIA, DIA)
    r.refresh_from_db()
    assert r.horas_ordinarias == Decimal("0.00")
    assert r.horas_recargo_nocturno == Decimal("2.00")
    assert r.parametros_id == nuevos.pk  # usó la nueva versión

    assert (
        AuditLog.objects.filter(accion=AuditLog.Accion.CONFIG_CAMBIADA).count()
        == audits_antes + 1
    )


# --------------------------------------------------------------------------
# (i) Auditor 403 al asignar turno
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_auditor_no_puede_asignar_turno():
    sede = _sede()
    emp = _empleado(sede)
    turno = _turno("Diurno", time(8, 0), time(16, 0))
    auditor = Usuario.objects.create_user(
        username="auditor1", password="ClaveSegura123", rol=Usuario.Rol.AUDITOR
    )
    client = APIClient()
    client.force_authenticate(user=auditor)

    resp = client.post(
        "/api/turnos/asignar/",
        {"empleado_id": emp.pk, "turno_id": turno.pk, "fecha_inicio": "2026-06-01"},
        format="json",
    )
    assert resp.status_code == 403
    assert AsignacionTurno.objects.count() == 0


# --------------------------------------------------------------------------
# Extra: poblador de festivos (Ley Emiliani)
# --------------------------------------------------------------------------
@pytest.mark.django_db
def test_poblar_festivos_command():
    call_command("poblar_festivos", 2026)
    assert DiaFestivo.objects.filter(fecha=date(2026, 1, 1)).exists()
    # Reyes Magos trasladado al lunes 12 de enero de 2026 (Ley Emiliani).
    assert DiaFestivo.objects.filter(fecha=date(2026, 1, 12)).exists()
    assert DiaFestivo.objects.count() == 18
