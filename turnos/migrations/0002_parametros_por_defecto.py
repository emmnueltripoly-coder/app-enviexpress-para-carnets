"""
Siembra los ParametrosLaborales por defecto vigentes en Colombia.

Valores editables (datos, no constantes de código). La franja nocturna inicia a
las 21:00 (Ley 2101 de 2021, vigente desde el 1-jul-2025). Porcentajes legales
de referencia: extra diurna 25%, extra nocturna 75%, recargo nocturno 35%,
dominical/festivo 75%. Jornada ordinaria diaria de referencia: 8 horas.
"""

from datetime import date, time
from decimal import Decimal

from django.db import migrations


def crear_parametros(apps, schema_editor):
    ParametrosLaborales = apps.get_model("turnos", "ParametrosLaborales")
    if not ParametrosLaborales.objects.exists():
        ParametrosLaborales.objects.create(
            descripcion="Valores por defecto (referencia Colombia)",
            inicio_jornada_nocturna=time(21, 0),
            fin_jornada_nocturna=time(6, 0),
            horas_jornada_ordinaria_diaria=Decimal("8.00"),
            porcentaje_extra_diurna=Decimal("25.00"),
            porcentaje_extra_nocturna=Decimal("75.00"),
            porcentaje_recargo_nocturno=Decimal("35.00"),
            porcentaje_dominical_festivo=Decimal("75.00"),
            vigente_desde=date(2025, 7, 1),
        )


def borrar_parametros(apps, schema_editor):
    ParametrosLaborales = apps.get_model("turnos", "ParametrosLaborales")
    ParametrosLaborales.objects.filter(
        descripcion="Valores por defecto (referencia Colombia)"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("turnos", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(crear_parametros, borrar_parametros),
    ]
