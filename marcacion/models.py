"""
Modelo Marcacion — núcleo de marcación (Hito 3).

INMUTABILIDAD (regla no negociable BASC: "Marcaciones inmutables"):
- En Python: save() rechaza ediciones (igual que AuditLog) y delete() está
  prohibido. Una corrección NO edita: crea un NUEVO registro con ``corrige_a``
  apuntando al original (patrón de reversión contable).
- En PostgreSQL: un trigger BEFORE UPDATE OR DELETE (migración 0002) aborta
  cualquier intento, incluso por SQL directo que evada el ORM.

ANTI-DOBLE-MARCACIÓN (concurrencia + fraude) — razonamiento del constraint:
- NO se usa UniqueConstraint(empleado, fecha, tipo): un empleado SÍ puede tener
  varias ENTRADA/SALIDA el mismo día (turnos partidos), así que eso bloquearía
  marcaciones legítimas.
- Lo que se debe evitar es el doble-submit / la marcación concurrente duplicada,
  que ocurre dentro de una ventana de segundos. Se usa la ventana que el propio
  enunciado propone ("el mismo minuto"): una columna derivada
  ``minuto_marcacion`` (timestamp truncado al minuto) + UniqueConstraint parcial
  sobre (empleado, tipo, minuto_marcacion) WHERE corrige_a IS NULL.
- El punto ciego del bucket (dos toques a ambos lados del cambio de minuto) se
  cubre en la capa de servicio con una verificación previa de ±60 s bajo
  select_for_update. Así: garantía dura por minuto en BD + verificación de
  ventana deslizante en la app.
- La condición ``corrige_a IS NULL`` exime a las correcciones administrativas.

OFFLINE (Hito 4, puerta abierta): ``es_offline`` y ``timestamp_dispositivo``
ya existen para el doble sello temporal; en este hito no se usan en la lógica.
"""

import uuid

from django.db import models
from django.utils import timezone


class Marcacion(models.Model):
    """Registro inmutable de una marcación de entrada/salida."""

    class Tipo(models.TextChoices):
        ENTRADA = "ENTRADA", "Entrada"
        SALIDA = "SALIDA", "Salida"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    empleado = models.ForeignKey(
        "personal.Empleado",
        on_delete=models.PROTECT,
        related_name="marcaciones",
    )
    sede = models.ForeignKey(
        "organizacion.Sede",
        on_delete=models.PROTECT,
        related_name="marcaciones",
    )
    tipo = models.CharField(max_length=10, choices=Tipo.choices)

    # --- Sellos temporales (integridad temporal BASC) -----------------------
    # HORA OFICIAL de la marcación: extraída del token QR firmado por el
    # servidor. Es la que cuenta para asistencia (no el celular ni el envío).
    # En marcación online se llena con la hora del QR escaneado; nullable para
    # correcciones (sin QR).
    timestamp_qr = models.DateTimeField(null=True, blank=True)
    # Sello del servidor (UTC): cuándo el servidor recibió/registró el dato.
    # En offline puede ser minutos/horas posterior a timestamp_qr. Se usa
    # default=timezone.now (en vez de auto_now_add) para derivar 'minuto_marcacion'
    # de forma consistente en save() antes del INSERT.
    timestamp_servidor = models.DateTimeField(default=timezone.now, db_index=True)
    # Sello del dispositivo (hora del celular al escanear). SOLO informativo:
    # nunca se confía en él. Nullable.
    timestamp_dispositivo = models.DateTimeField(null=True, blank=True)

    # Clave anti-duplicado: la hora OFICIAL truncada al minuto (timestamp_qr si
    # existe, si no timestamp_servidor). Derivada en save(); no editable.
    minuto_marcacion = models.DateTimeField(editable=False, db_index=True)

    # Coordenadas reportadas por el empleado al marcar.
    latitud = models.DecimalField(max_digits=9, decimal_places=6)
    longitud = models.DecimalField(max_digits=9, decimal_places=6)

    # Geocerca FLEXIBLE: no se bloquea; se marca para revisión de RRHH.
    fuera_de_sede = models.BooleanField(default=False)
    distancia_metros = models.DecimalField(max_digits=10, decimal_places=2)

    es_offline = models.BooleanField(default=False)
    # Bandera de revisión RRHH (NO bloqueo) para casos offline sospechosos:
    # QR muy antiguo, o desfase grosero del timestamp_dispositivo.
    revisar_offline = models.BooleanField(default=False)

    # Identificador único del token QR (jti). Clave de anti-replay/idempotencia.
    # El MISMO QR del kiosco lo escanean varios empleados en su ventana de 45 s,
    # por eso la unicidad es por (empleado, qr_jti), NO global. Nullable para
    # correcciones (sin QR).
    qr_jti = models.CharField(max_length=32, null=True, blank=True)

    # Corrección contable: una marcación que corrige a otra anterior.
    corrige_a = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="correcciones",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "marcacion"
        verbose_name = "Marcación"
        verbose_name_plural = "Marcaciones"
        ordering = ("-timestamp_servidor",)
        indexes = [
            models.Index(fields=["empleado", "tipo", "timestamp_servidor"]),
            models.Index(fields=["sede", "timestamp_servidor"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["empleado", "tipo", "minuto_marcacion"],
                condition=models.Q(corrige_a__isnull=True),
                name="uniq_marcacion_empleado_tipo_minuto",
            ),
            # Anti-replay/idempotencia: un empleado no reutiliza el mismo QR.
            # Distintos empleados SÍ comparten el QR del kiosco -> incluye empleado.
            models.UniqueConstraint(
                fields=["empleado", "qr_jti"],
                condition=models.Q(qr_jti__isnull=False),
                name="uniq_marcacion_empleado_qrjti",
            ),
        ]

    def __str__(self):
        return f"{self.tipo} de {self.empleado_id} @ {self.timestamp_servidor:%Y-%m-%d %H:%M:%S}"

    def save(self, *args, **kwargs):
        """Inmutable: permite el INSERT inicial pero bloquea cualquier edición."""
        if not self._state.adding:
            raise ValueError(
                "Marcacion es inmutable: una marcación no puede modificarse. "
                "Para corregir, cree una nueva con 'corrige_a'."
            )
        if self.minuto_marcacion is None:
            # La clave anti-duplicado usa la hora OFICIAL: timestamp_qr cuando
            # existe (incl. offline), si no el sello del servidor.
            base = self.timestamp_qr or self.timestamp_servidor
            self.minuto_marcacion = base.replace(second=0, microsecond=0)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Inmutable: una marcación nunca se borra."""
        raise ValueError("Marcacion es inmutable: una marcación no puede borrarse.")
