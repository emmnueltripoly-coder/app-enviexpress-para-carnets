"""
Servicios del Hito 5: asignación de turnos, parámetros versionados y el MOTOR
de clasificación de horas.

Reglas de integridad temporal del motor:
- Toda comparación de "reloj de pared" (franja nocturna, festivo, turno) se hace
  en hora LOCAL (America/Bogota), convirtiendo la hora oficial (UTC) con
  timezone.localtime. Las duraciones son absolutas (Colombia es UTC-5 fijo).
- La hora OFICIAL de una marcación es timestamp_qr si existe, si no
  timestamp_servidor (Coalesce).
- Clasificación minuto a minuto; cada minuto cae en UN solo bucket. Precedencia:
  festivo > extra (nocturna/diurna) > ordinaria (nocturna=recargo / diurna).
  Así la suma de buckets == tiempo trabajado y el resultado es recalculable.
  (Nómina real puede apilar recargos; aquí se deja el dato crudo clasificado con
  todas las fronteras configurables vía ParametrosLaborales/DiaFestivo.)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django.db import transaction
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from auditoria.models import AuditLog
from auditoria.services import AuditService
from marcacion.models import Marcacion
from personal.models import Empleado

from .models import (
    AsignacionTurno,
    DiaFestivo,
    ParametrosLaborales,
    ResumenJornada,
    Turno,
)


# --------------------------------------------------------------------------
# Asignación de turnos (auditada)
# --------------------------------------------------------------------------
def turno_vigente(empleado: Empleado, fecha) -> Optional[Turno]:
    """Turno asignado al empleado en una fecha (fijo o rotativo).

    Elige la asignación activa que cubre la fecha con el fecha_inicio más
    reciente (las rotativas no deben solaparse; si lo hicieran, gana la última).
    """
    asignacion = (
        AsignacionTurno.objects.filter(
            empleado=empleado, activo=True, fecha_inicio__lte=fecha
        )
        .filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha))
        .select_related("turno")
        .order_by("-fecha_inicio")
        .first()
    )
    return asignacion.turno if asignacion else None


@transaction.atomic
def asignar_turno(
    *,
    empleado: Empleado,
    turno: Turno,
    fecha_inicio,
    fecha_fin=None,
    actor_id: Optional[str] = None,
    actor_rol: Optional[str] = None,
    ip_origen: Optional[str] = None,
) -> AsignacionTurno:
    """Crea una AsignacionTurno y la registra en audit_log (TURNO_CAMBIADO)."""
    asignacion = AsignacionTurno.objects.create(
        empleado=empleado,
        turno=turno,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    AuditService.registrar(
        accion=AuditLog.Accion.TURNO_CAMBIADO,
        entidad="AsignacionTurno",
        entidad_id=str(asignacion.pk),
        actor_id=actor_id,
        actor_rol=actor_rol,
        ip_origen=ip_origen,
        metadata={
            "empleado_id": empleado.pk,
            "turno_id": turno.pk,
            "fecha_inicio": str(fecha_inicio),
            "fecha_fin": str(fecha_fin) if fecha_fin else None,
        },
    )
    return asignacion


# --------------------------------------------------------------------------
# Parámetros laborales versionados (auditados)
# --------------------------------------------------------------------------
@transaction.atomic
def crear_version_parametros(
    *,
    inicio_jornada_nocturna,
    fin_jornada_nocturna,
    horas_jornada_ordinaria_diaria,
    porcentaje_extra_diurna,
    porcentaje_extra_nocturna,
    porcentaje_recargo_nocturno,
    porcentaje_dominical_festivo,
    vigente_desde,
    descripcion="",
    actor_id: Optional[str] = None,
    actor_rol: Optional[str] = None,
    ip_origen: Optional[str] = None,
) -> ParametrosLaborales:
    """Crea una NUEVA versión de parámetros y la audita (CONFIG_CAMBIADA)."""
    parametros = ParametrosLaborales.objects.create(
        inicio_jornada_nocturna=inicio_jornada_nocturna,
        fin_jornada_nocturna=fin_jornada_nocturna,
        horas_jornada_ordinaria_diaria=horas_jornada_ordinaria_diaria,
        porcentaje_extra_diurna=porcentaje_extra_diurna,
        porcentaje_extra_nocturna=porcentaje_extra_nocturna,
        porcentaje_recargo_nocturno=porcentaje_recargo_nocturno,
        porcentaje_dominical_festivo=porcentaje_dominical_festivo,
        vigente_desde=vigente_desde,
        descripcion=descripcion,
    )
    AuditService.registrar(
        accion=AuditLog.Accion.CONFIG_CAMBIADA,
        entidad="ParametrosLaborales",
        entidad_id=str(parametros.pk),
        actor_id=actor_id,
        actor_rol=actor_rol,
        ip_origen=ip_origen,
        metadata={
            "vigente_desde": str(vigente_desde),
            "inicio_jornada_nocturna": str(inicio_jornada_nocturna),
            "fin_jornada_nocturna": str(fin_jornada_nocturna),
            "horas_jornada_ordinaria_diaria": str(horas_jornada_ordinaria_diaria),
            "porcentaje_recargo_nocturno": str(porcentaje_recargo_nocturno),
        },
    )
    return parametros


# --------------------------------------------------------------------------
# Motor de clasificación de horas
# --------------------------------------------------------------------------
def en_franja_nocturna(t: time, params: ParametrosLaborales) -> bool:
    """¿La hora local t está dentro de la franja nocturna (puede cruzar 00:00)?"""
    inicio = params.inicio_jornada_nocturna
    fin = params.fin_jornada_nocturna
    if inicio <= fin:
        return inicio <= t < fin
    # Franja que cruza medianoche (p. ej. 21:00 -> 06:00).
    return t >= inicio or t < fin


def _a_horas(minutos: int) -> Decimal:
    return (Decimal(minutos) / Decimal(60)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _festivos_set(fecha_inicio, fecha_fin):
    """Conjunto de fechas festivas en el rango (incluye un día extra por cruces)."""
    return set(
        DiaFestivo.objects.filter(
            fecha__gte=fecha_inicio, fecha__lte=fecha_fin + timedelta(days=1)
        ).values_list("fecha", flat=True)
    )


def clasificar_jornada(entrada_local, salida_local, turno, params, festivos):
    """Clasifica los minutos trabajados entre entrada y salida (hora LOCAL).

    Devuelve un dict con minutos por bucket + tardanza/salida_temprana.
    """
    limite_ordinaria_min = int(params.horas_jornada_ordinaria_diaria * 60)

    contadores = {
        "ordinarias": 0,
        "extra_diurnas": 0,
        "extra_nocturnas": 0,
        "recargo_nocturno": 0,
        "dominical_festivo": 0,
    }

    minuto = entrada_local
    indice = 0
    while minuto < salida_local:
        es_festivo = minuto.weekday() == 6 or minuto.date() in festivos
        es_nocturno = en_franja_nocturna(minuto.time(), params)
        es_extra = indice >= limite_ordinaria_min

        if es_festivo:
            contadores["dominical_festivo"] += 1
        elif es_extra:
            contadores["extra_nocturnas" if es_nocturno else "extra_diurnas"] += 1
        else:
            contadores["recargo_nocturno" if es_nocturno else "ordinarias"] += 1

        minuto += timedelta(minutes=1)
        indice += 1

    tardanza, salida_temprana = _desviaciones_turno(
        entrada_local, salida_local, turno
    )

    return {
        **{k: _a_horas(v) for k, v in contadores.items()},
        "tardanza_minutos": tardanza,
        "salida_temprana_minutos": salida_temprana,
    }


def _desviaciones_turno(entrada_local, salida_local, turno):
    """Tardanza (entrada tardía) y salida temprana en minutos, según el turno."""
    if turno is None:
        return 0, 0
    tz = timezone.get_current_timezone()
    fecha = entrada_local.date()

    inicio_turno = timezone.make_aware(
        datetime.combine(fecha, turno.hora_inicio), tz
    )
    fin_fecha = fecha + timedelta(days=1) if turno.cruza_medianoche else fecha
    fin_turno = timezone.make_aware(
        datetime.combine(fin_fecha, turno.hora_fin), tz
    )

    tardanza = max(0, round((entrada_local - inicio_turno).total_seconds() / 60))
    salida_temprana = max(
        0, round((fin_turno - salida_local).total_seconds() / 60)
    )
    return int(tardanza), int(salida_temprana)


def _emparejar_jornadas(empleado: Empleado, fecha_inicio, fecha_fin):
    """Empareja ENTRADA->SALIDA usando la hora oficial; devuelve (entrada, salida).

    Excluye marcaciones corregidas (superadas por una corrección). Cada jornada
    se atribuye a la fecha local de la ENTRADA.
    """
    tz = timezone.get_current_timezone()
    inicio_dt = timezone.make_aware(datetime.combine(fecha_inicio, time.min), tz)
    # Ventana extendida +1 día para capturar salidas tras la medianoche.
    fin_dt = timezone.make_aware(
        datetime.combine(fecha_fin + timedelta(days=1), time.max), tz
    )

    superadas = set(
        Marcacion.objects.filter(
            empleado=empleado, corrige_a__isnull=False
        ).values_list("corrige_a_id", flat=True)
    )

    marcaciones = (
        Marcacion.objects.filter(empleado=empleado)
        .annotate(oficial=Coalesce("timestamp_qr", "timestamp_servidor"))
        .filter(oficial__gte=inicio_dt, oficial__lte=fin_dt)
        .order_by("oficial")
    )

    jornadas = []
    entrada_pendiente = None
    for m in marcaciones:
        if m.pk in superadas:
            continue
        if m.tipo == Marcacion.Tipo.ENTRADA:
            entrada_pendiente = m
        elif m.tipo == Marcacion.Tipo.SALIDA and entrada_pendiente is not None:
            jornadas.append((entrada_pendiente, m))
            entrada_pendiente = None

    # Solo jornadas cuya ENTRADA cae dentro del rango solicitado.
    resultado = []
    for entrada, salida in jornadas:
        fecha_entrada = timezone.localtime(entrada.oficial).date()
        if fecha_inicio <= fecha_entrada <= fecha_fin:
            resultado.append((entrada, salida))
    return resultado


@transaction.atomic
def calcular_jornadas(empleado: Empleado, fecha_inicio, fecha_fin) -> list:
    """Recalcula y persiste los ResumenJornada del empleado en el rango.

    Devuelve la lista de ResumenJornada. Es idempotente (update_or_create por
    empleado+fecha): NO toca las marcaciones; el resumen es derivado.
    """
    festivos = _festivos_set(fecha_inicio, fecha_fin)
    jornadas = _emparejar_jornadas(empleado, fecha_inicio, fecha_fin)
    ahora = timezone.now()
    resumenes = []

    for entrada, salida in jornadas:
        entrada_local = timezone.localtime(entrada.oficial)
        salida_local = timezone.localtime(salida.oficial)
        fecha = entrada_local.date()

        params = ParametrosLaborales.vigentes_para(fecha)
        if params is None:
            # Sin parámetros vigentes no se puede clasificar; se omite.
            continue
        turno = turno_vigente(empleado, fecha)

        clasificacion = clasificar_jornada(
            entrada_local, salida_local, turno, params, festivos
        )

        resumen, _ = ResumenJornada.objects.update_or_create(
            empleado=empleado,
            fecha=fecha,
            defaults={
                "turno": turno,
                "hora_entrada": entrada.oficial,
                "hora_salida": salida.oficial,
                "horas_ordinarias": clasificacion["ordinarias"],
                "horas_extra_diurnas": clasificacion["extra_diurnas"],
                "horas_extra_nocturnas": clasificacion["extra_nocturnas"],
                "horas_recargo_nocturno": clasificacion["recargo_nocturno"],
                "horas_dominical_festivo": clasificacion["dominical_festivo"],
                "tardanza_minutos": clasificacion["tardanza_minutos"],
                "salida_temprana_minutos": clasificacion["salida_temprana_minutos"],
                "parametros": params,
                "calculado_at": ahora,
            },
        )
        resumenes.append(resumen)

    return resumenes
