"""Serializers de marcación (Hito 3)."""

from rest_framework import serializers

from .models import Marcacion


class MarcacionInputSerializer(serializers.Serializer):
    """Payload de marcación enviado por la app del empleado."""

    token_qr = serializers.CharField()
    tipo = serializers.ChoiceField(choices=Marcacion.Tipo.choices)
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6)


class CorreccionInputSerializer(serializers.Serializer):
    """Payload de corrección (RRHH/Admin). No incluye token QR."""

    tipo = serializers.ChoiceField(choices=Marcacion.Tipo.choices)
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    motivo = serializers.CharField(required=False, allow_blank=True, default="")


class MarcacionSerializer(serializers.ModelSerializer):
    """Representación de salida de una marcación."""

    class Meta:
        model = Marcacion
        fields = (
            "id",
            "empleado",
            "sede",
            "tipo",
            "timestamp_servidor",
            "timestamp_dispositivo",
            "latitud",
            "longitud",
            "fuera_de_sede",
            "distancia_metros",
            "es_offline",
            "corrige_a",
            "created_at",
        )
        read_only_fields = fields
