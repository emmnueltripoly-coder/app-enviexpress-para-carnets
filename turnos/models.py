"""
Modelos de turnos y parámetros laborales (Hito 5).

Alcance: el sistema CLASIFICA y CUENTA horas (ordinarias, extra diurnas/
nocturnas, recargo nocturno, dominical/festivo). NO calcula valores en pesos
(eso es nómina, fuera del MVP). Las fronteras horarias y los porcentajes son
CONFIGURABLES y versionados por vigencia, porque la ley laboral colombiana
cambia con reformas.
"""

from django.db import models

from common.models import SoftDeleteModel


class Turno(SoftDeleteModel):
    """Definición de un turno. hora_inicio/hora_fin son hora local (Bogotá)."""

    nombre = models.CharField(max_length=120)
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField()
    # Turnos nocturnos cuya hora_fin cae al día siguiente (p. ej. 22:00 -> 06:00).
    cruza_medianoche = models.BooleanField(default=False)
    sede = models.ForeignKey(
        "organizacion.Sede",
        on_delete=models.PROTECT,
        related_name="turnos",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "turno"
        verbose_name = "Turno"
        verbose_name_plural = "Turnos"
        ordering = ("nombre",)

    def __str__(self):
        return f"{self.nombre} ({self.hora_inicio:%H:%M}-{self.hora_fin:%H:%M})"


class AsignacionTurno(SoftDeleteModel):
    """Vincula Empleado + Turno en un rango de fechas.

    Modela tanto turnos FIJOS como ROTATIVOS con la misma estructura:
    - FIJO: una asignación abierta (fecha_fin = NULL) que cubre indefinidamente.
    - ROTATIVO: varias asignaciones con rangos (p. ej. una por semana), que NO
      deben solaparse. Para una fecha dada se elige la asignación vigente con
      el fecha_inicio más reciente que la cubra.
    """

    empleado = models.ForeignKey(
        "personal.Empleado",
        on_delete=models.PROTECT,
        related_name="asignaciones_turno",
    )
    turno = models.ForeignKey(
        Turno,
        on_delete=models.PROTECT,
        related_name="asignaciones",
    )
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "asignacion_turno"
        verbose_name = "Asignación de turno"
        verbose_name_plural = "Asignaciones de turno"
        ordering = ("-fecha_inicio",)
        indexes = [
            models.Index(fields=["empleado", "fecha_inicio"]),
        ]

    def __str__(self):
        return f"{self.empleado_id} -> {self.turno_id} desde {self.fecha_inicio}"

    def cubre(self, fecha) -> bool:
        if fecha < self.fecha_inicio:
            return False
        if self.fecha_fin is not None and fecha > self.fecha_fin:
            return False
        return True


class ParametrosLaborales(models.Model):
    """Parámetros legales CONFIGURABLES y versionados por fecha de vigencia.

    Un "cambio" se modela creando una NUEVA versión (vigente_desde). Para una
    fecha dada rigen los parámetros con el vigente_desde más reciente <= fecha
    (desempate por id). Así el histórico queda trazable y un recálculo de una
    jornada pasada puede usar los parámetros que regían entonces.
    """

    descripcion = models.CharField(max_length=200, blank=True, default="")

    # Fronteras de la jornada nocturna (hora local). Puede cruzar medianoche.
    inicio_jornada_nocturna = models.TimeField()
    fin_jornada_nocturna = models.TimeField()

    horas_jornada_ordinaria_diaria = models.DecimalField(
        max_digits=4, decimal_places=2
    )

    # Porcentajes de recargo (solo para nómina futura; aquí no se aplican a $).
    porcentaje_extra_diurna = models.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_extra_nocturna = models.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_recargo_nocturno = models.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_dominical_festivo = models.DecimalField(max_digits=5, decimal_places=2)

    vigente_desde = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "parametros_laborales"
        verbose_name = "Parámetros laborales"
        verbose_name_plural = "Parámetros laborales"
        ordering = ("-vigente_desde", "-id")

    def __str__(self):
        return f"Parámetros vigentes desde {self.vigente_desde}"

    @classmethod
    def vigentes_para(cls, fecha):
        """Devuelve la versión vigente para una fecha (o None si no hay)."""
        return (
            cls.objects.filter(vigente_desde__lte=fecha)
            .order_by("-vigente_desde", "-id")
            .first()
        )


class DiaFestivo(models.Model):
    """Calendario de festivos de Colombia. Se consulta; nunca se calcula a mano
    en la lógica de horas."""

    fecha = models.DateField(unique=True)
    descripcion = models.CharField(max_length=200)

    class Meta:
        db_table = "dia_festivo"
        verbose_name = "Día festivo"
        verbose_name_plural = "Días festivos"
        ordering = ("fecha",)

    def __str__(self):
        return f"{self.fecha} — {self.descripcion}"


class ResumenJornada(models.Model):
    """Resultado DERIVADO de clasificar las marcaciones de una jornada.

    Es recalculable (update_or_create por empleado+fecha) y registra cuándo y
    con qué parámetros se calculó. NO sustituye a las marcaciones (inmutables);
    es un agregado para reportes/nómina futura.
    """

    empleado = models.ForeignKey(
        "personal.Empleado",
        on_delete=models.PROTECT,
        related_name="resumenes_jornada",
    )
    fecha = models.DateField()
    turno = models.ForeignKey(
        Turno, on_delete=models.PROTECT, null=True, blank=True
    )

    hora_entrada = models.DateTimeField(null=True, blank=True)
    hora_salida = models.DateTimeField(null=True, blank=True)

    horas_ordinarias = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    horas_extra_diurnas = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    horas_extra_nocturnas = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    horas_recargo_nocturno = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    horas_dominical_festivo = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    tardanza_minutos = models.PositiveIntegerField(default=0)
    salida_temprana_minutos = models.PositiveIntegerField(default=0)

    # Trazabilidad del cálculo.
    parametros = models.ForeignKey(
        ParametrosLaborales, on_delete=models.PROTECT, null=True, blank=True
    )
    calculado_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "resumen_jornada"
        verbose_name = "Resumen de jornada"
        verbose_name_plural = "Resúmenes de jornada"
        ordering = ("-fecha",)
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "fecha"], name="uniq_resumen_empleado_fecha"
            ),
        ]

    def __str__(self):
        return f"Resumen {self.empleado_id} {self.fecha}"
