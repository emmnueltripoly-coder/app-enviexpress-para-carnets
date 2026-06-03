"""Serializers de novedades (Hito 6)."""

from django.conf import settings
from rest_framework import serializers

from .models import Novedad, SoporteNovedad


class NovedadInputSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=Novedad.Tipo.choices)
    descripcion = serializers.CharField()
    fecha_inicio = serializers.DateField()
    fecha_fin = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        fin = attrs.get("fecha_fin")
        if fin and fin < attrs["fecha_inicio"]:
            raise serializers.ValidationError(
                "fecha_fin no puede ser anterior a fecha_inicio."
            )
        return attrs


class NovedadSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    soportes_count = serializers.IntegerField(source="soportes.count", read_only=True)

    class Meta:
        model = Novedad
        fields = (
            "id",
            "empleado",
            "tipo",
            "tipo_display",
            "descripcion",
            "fecha_inicio",
            "fecha_fin",
            "estado",
            "estado_display",
            "soportes_count",
            "created_at",
        )
        read_only_fields = fields


class SoporteUploadSerializer(serializers.Serializer):
    archivo = serializers.FileField()

    def validate_archivo(self, archivo):
        # Tamaño máximo.
        if archivo.size > settings.SOPORTE_MAX_BYTES:
            maximo_mb = settings.SOPORTE_MAX_BYTES / (1024 * 1024)
            raise serializers.ValidationError(
                f"El archivo supera el tamaño máximo permitido ({maximo_mb:.0f} MB)."
            )
        # Tipo permitido (imagen o PDF).
        tipo = getattr(archivo, "content_type", None)
        if tipo not in settings.SOPORTE_MIME_PERMITIDOS:
            raise serializers.ValidationError(
                "Tipo de archivo no permitido. Solo se aceptan imágenes (JPG/PNG) o PDF."
            )
        return archivo


class SoporteMetadatosSerializer(serializers.ModelSerializer):
    """Metadatos del soporte (sin el contenido del archivo)."""

    class Meta:
        model = SoporteNovedad
        fields = (
            "id",
            "novedad",
            "nombre_original",
            "tipo_mime",
            "tamano_bytes",
            "subido_por",
            "created_at",
        )
        read_only_fields = fields


class CambioEstadoSerializer(serializers.Serializer):
    comentario = serializers.CharField(required=False, allow_blank=True, default="")
