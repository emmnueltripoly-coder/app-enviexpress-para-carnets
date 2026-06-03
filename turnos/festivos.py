"""
Festivos de Colombia.

Calcula los festivos de un año aplicando:
- Festivos de fecha fija (no se trasladan).
- Ley Emiliani (Ley 51 de 1983): varios festivos se trasladan al lunes
  siguiente cuando no caen en lunes.
- Festivos móviles basados en la Pascua (Domingo de Resurrección), calculada
  con el algoritmo de Computus (Gregoriano anónimo). Jueves y Viernes Santo NO
  se trasladan; Ascensión, Corpus Christi y Sagrado Corazón SÍ (Emiliani).

Esta es la ÚNICA fuente para poblar la tabla DiaFestivo; la lógica de horas
nunca calcula festivos: los consulta de la tabla.
"""

from datetime import date, timedelta


def domingo_de_pascua(anio: int) -> date:
    """Domingo de Resurrección (algoritmo de Computus, calendario Gregoriano)."""
    a = anio % 19
    b = anio // 100
    c = anio % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return date(anio, mes, dia)


def _trasladar_a_lunes(fecha: date) -> date:
    """Ley Emiliani: si no es lunes, traslada al lunes siguiente."""
    # weekday(): lunes=0 ... domingo=6
    if fecha.weekday() == 0:
        return fecha
    return fecha + timedelta(days=(7 - fecha.weekday()))


def festivos_colombia(anio: int) -> list[tuple[date, str]]:
    """Lista de (fecha, descripción) de los festivos colombianos del año."""
    pascua = domingo_de_pascua(anio)

    # Fijos (no se trasladan).
    fijos = [
        (date(anio, 1, 1), "Año Nuevo"),
        (date(anio, 5, 1), "Día del Trabajo"),
        (date(anio, 7, 20), "Día de la Independencia"),
        (date(anio, 8, 7), "Batalla de Boyacá"),
        (date(anio, 12, 8), "Inmaculada Concepción"),
        (date(anio, 12, 25), "Navidad"),
    ]

    # Relativos a Pascua que NO se trasladan.
    semana_santa = [
        (pascua - timedelta(days=3), "Jueves Santo"),
        (pascua - timedelta(days=2), "Viernes Santo"),
    ]

    # Trasladables por Ley Emiliani (fecha base -> lunes siguiente).
    emiliani_fijos = [
        (date(anio, 1, 6), "Reyes Magos"),
        (date(anio, 3, 19), "Día de San José"),
        (date(anio, 6, 29), "San Pedro y San Pablo"),
        (date(anio, 8, 15), "Asunción de la Virgen"),
        (date(anio, 10, 12), "Día de la Raza"),
        (date(anio, 11, 1), "Todos los Santos"),
        (date(anio, 11, 11), "Independencia de Cartagena"),
    ]
    emiliani_pascua = [
        (pascua + timedelta(days=39), "Ascensión del Señor"),
        (pascua + timedelta(days=60), "Corpus Christi"),
        (pascua + timedelta(days=68), "Sagrado Corazón de Jesús"),
    ]

    festivos = list(fijos) + list(semana_santa)
    for base, nombre in emiliani_fijos + emiliani_pascua:
        festivos.append((_trasladar_a_lunes(base), nombre))

    festivos.sort(key=lambda x: x[0])
    return festivos
