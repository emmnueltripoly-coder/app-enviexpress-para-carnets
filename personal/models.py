"""
Modelos de personal: Usuario (custom), Empleado y ConsentimientoHabeasData.

Decisiones de diseño sobre datos personales (Ley 1581 / Habeas Data):
- Los DATOS PERSONALES sensibles (documento, nombres, apellidos) viven SOLO en
  ``Empleado``, no en ``Usuario``. ``Usuario`` se mantiene mínimo: credenciales
  de acceso + ``rol``. Los campos ``first_name``/``last_name`` heredados de
  ``AbstractUser`` se dejan vacíos; la fuente de verdad es ``Empleado``.
- ``ConsentimientoHabeasData`` es INMUTABLE: una vez registrado no se edita ni
  se borra (registro legal del consentimiento). Si la política cambia de
  versión, se crea un NUEVO registro.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models

from common.models import SoftDeleteModel


class Usuario(AbstractUser):
    """Usuario del sistema (autenticación). Modelo personalizado con ``rol``.

    AUTH_USER_MODEL apunta a este modelo. NO almacena datos personales
    sensibles (esos van en ``Empleado``).
    """

    class Rol(models.TextChoices):
        EMPLEADO = "EMPLEADO", "Empleado"
        SUPERVISOR = "SUPERVISOR", "Supervisor"
        RRHH = "RRHH", "RRHH"
        AUDITOR = "AUDITOR", "Auditor"
        ADMIN = "ADMIN", "Admin"

    rol = models.CharField(
        max_length=20,
        choices=Rol.choices,
        default=Rol.EMPLEADO,
    )

    class Meta:
        db_table = "usuario"
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"


class Empleado(SoftDeleteModel):
    """Empleado de la empresa. Contiene los datos personales (Habeas Data).

    Soft-delete vía ``activo`` (heredado de SoftDeleteModel): un empleado nunca
    se borra físicamente; se da de baja con ``desactivar()``.
    """

    usuario = models.OneToOneField(
        Usuario,
        on_delete=models.PROTECT,  # sin borrado físico en cascada
        related_name="empleado",
    )
    # Documento de identidad: dato personal, identificador único de la persona.
    documento_identidad = models.CharField(max_length=20, unique=True)
    nombres = models.CharField(max_length=150)
    apellidos = models.CharField(max_length=150)

    sede = models.ForeignKey(
        "organizacion.Sede",
        on_delete=models.PROTECT,
        related_name="empleados",
    )
    cargo = models.CharField(max_length=150)
    fecha_ingreso = models.DateField()

    class Meta:
        db_table = "empleado"
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"
        ordering = ("apellidos", "nombres")

    def __str__(self):
        return f"{self.nombres} {self.apellidos} ({self.documento_identidad})"

    @property
    def nombre_completo(self):
        return f"{self.nombres} {self.apellidos}"


class ConsentimientoHabeasData(models.Model):
    """Registro INMUTABLE del consentimiento Habeas Data de un empleado.

    Ley 1581: se guarda el texto EXACTO de la política aceptada, la versión, la
    fecha y la IP. Un empleado puede tener varios registros (uno por versión de
    política). Los registros nunca se editan ni se borran: una corrección o un
    cambio de versión es siempre un NUEVO registro.
    """

    empleado = models.ForeignKey(
        Empleado,
        on_delete=models.PROTECT,
        related_name="consentimientos",
    )
    version_politica = models.CharField(max_length=50)
    aceptado = models.BooleanField()
    fecha_aceptacion = models.DateTimeField()
    ip_aceptacion = models.GenericIPAddressField()
    # Copia literal del texto que el titular aceptó (evidencia legal).
    texto_politica = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "consentimiento_habeas_data"
        verbose_name = "Consentimiento Habeas Data"
        verbose_name_plural = "Consentimientos Habeas Data"
        ordering = ("-fecha_aceptacion",)

    def __str__(self):
        estado = "aceptado" if self.aceptado else "rechazado"
        return f"Consentimiento v{self.version_politica} de {self.empleado} ({estado})"

    def save(self, *args, **kwargs):
        """Inmutable: permite el INSERT inicial pero bloquea cualquier edición."""
        if not self._state.adding:
            raise ValueError(
                "ConsentimientoHabeasData es inmutable: un consentimiento "
                "registrado no puede modificarse. Cree un nuevo registro."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Inmutable: un registro de consentimiento legal no puede borrarse."""
        raise ValueError(
            "ConsentimientoHabeasData es inmutable: no puede borrarse."
        )
