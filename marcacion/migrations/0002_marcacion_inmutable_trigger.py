"""
Trigger PL/pgSQL que hace la tabla marcacion inmutable a nivel de base de datos.

CLAUDE.md (regla no negociable): "Marcaciones inmutables. Un registro de
marcación nunca se edita ni se borra." Igual que con audit_log, la inmutabilidad
no se confía solo al ORM: un trigger BEFORE UPDATE OR DELETE aborta con EXCEPTION
cualquier intento, incluso por SQL directo. Las correcciones son INSERT nuevos
(corrige_a), nunca UPDATE, así que este trigger no las afecta.
"""

from django.db import migrations


SQL_CREAR = r"""
CREATE OR REPLACE FUNCTION marcacion_inmutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'marcacion es inmutable: operacion % no permitida. Para corregir, cree una nueva marcacion con corrige_a.',
        TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_marcacion_inmutable ON marcacion;

CREATE TRIGGER trg_marcacion_inmutable
    BEFORE UPDATE OR DELETE ON marcacion
    FOR EACH ROW
    EXECUTE FUNCTION marcacion_inmutable();
"""

SQL_REVERTIR = r"""
DROP TRIGGER IF EXISTS trg_marcacion_inmutable ON marcacion;
DROP FUNCTION IF EXISTS marcacion_inmutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("marcacion", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=SQL_CREAR, reverse_sql=SQL_REVERTIR),
    ]
