"""Serializers de marcación (Hitos 3 y 4)."""

from rest_framework import serializers

from .models import Marcacion


class SyncItemSerializer(serializers.Serializer):
    """Un ítem de marcación offline dentro del lote de sincronización."""

    token_qr = serializers.CharField()
    tipo = serializers.ChoiceField(choices=Marcacion.Tipo.choices)
    latitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitud = serializers.DecimalField(max_digits=9, decimal_places=6)
    # Hora del celular al escanear: SOLO informativa, opcional.
    timestamp_dispositivo = serializers.DateTimeField(required=False, allow_null=True)


class SyncBatchSerializer(serializers.Serializer):
    """Lote de marcaciones offline pendientes de sincronizar."""

    marcaciones = SyncItemSerializer(many=True, allow_empty=False)


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
            "timestamp_qr",
            "timestamp_servidor",
            "timestamp_dispositivo",
            "latitud",
            "longitud",
            "fuera_de_sede",
            "distancia_metros",
            "es_offline",
            "revisar_offline",
            "qr_jti",
            "corrige_a",
            "created_at",
        )
        read_only_fields = fields
