"""Serializers del Hito 5."""

from rest_framework import serializers

from .models import ParametrosLaborales, ResumenJornada


class AsignarTurnoSerializer(serializers.Serializer):
    empleado_id = serializers.IntegerField()
    turno_id = serializers.IntegerField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField(required=False, allow_null=True)


class ParametrosInputSerializer(serializers.Serializer):
    inicio_jornada_nocturna = serializers.TimeField()
    fin_jornada_nocturna = serializers.TimeField()
    horas_jornada_ordinaria_diaria = serializers.DecimalField(
        max_digits=4, decimal_places=2
    )
    porcentaje_extra_diurna = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_extra_nocturna = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_recargo_nocturno = serializers.DecimalField(max_digits=5, decimal_places=2)
    porcentaje_dominical_festivo = serializers.DecimalField(
        max_digits=5, decimal_places=2
    )
    vigente_desde = serializers.DateField()
    descripcion = serializers.CharField(required=False, allow_blank=True, default="")


class RecalcularSerializer(serializers.Serializer):
    empleado_id = serializers.IntegerField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField()


class ResumenJornadaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumenJornada
        fields = (
            "id",
            "empleado",
            "fecha",
            "turno",
            "hora_entrada",
            "hora_salida",
            "horas_ordinarias",
            "horas_extra_diurnas",
            "horas_extra_nocturnas",
            "horas_recargo_nocturno",
            "horas_dominical_festivo",
            "tardanza_minutos",
            "salida_temprana_minutos",
            "parametros",
            "calculado_at",
        )
        read_only_fields = fields


class ParametrosLaboralesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametrosLaborales
        fields = "__all__"
        read_only_fields = ("id", "created_at")
