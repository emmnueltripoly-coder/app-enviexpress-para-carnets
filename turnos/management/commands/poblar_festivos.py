"""Puebla la tabla DiaFestivo con los festivos de Colombia.

Por defecto puebla el año en curso y el siguiente. Idempotente.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from turnos.festivos import festivos_colombia
from turnos.models import DiaFestivo


class Command(BaseCommand):
    help = "Puebla los días festivos de Colombia (año actual y siguiente por defecto)."

    def add_arguments(self, parser):
        parser.add_argument(
            "anios",
            nargs="*",
            type=int,
            help="Años a poblar. Si se omite, usa el actual y el siguiente.",
        )

    def handle(self, *args, **options):
        anios = options["anios"]
        if not anios:
            actual = timezone.localdate().year
            anios = [actual, actual + 1]

        creados = 0
        for anio in anios:
            for fecha, descripcion in festivos_colombia(anio):
                _, creado = DiaFestivo.objects.get_or_create(
                    fecha=fecha, defaults={"descripcion": descripcion}
                )
                creados += int(creado)

        self.stdout.write(
            self.style.SUCCESS(
                f"Festivos poblados para {anios}. Nuevos registros: {creados}."
            )
        )
