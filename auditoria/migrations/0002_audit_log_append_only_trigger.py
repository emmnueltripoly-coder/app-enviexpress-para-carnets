"""
Trigger PL/pgSQL que hace la tabla audit_log estrictamente append-only.

Defensa a nivel de base de datos (no solo de Python): cualquier intento de
UPDATE o DELETE sobre audit_log —incluso por SQL directo que evada el ORM de
Django— aborta con EXCEPTION. Requisito BASC / Ley 1581: log de auditoría
inalterable.
"""

from django.db import migrations


# Función de trigger: ante cualquier UPDATE o DELETE lanza EXCEPTION.
SQL_CREAR = r"""
CREATE OR REPLACE FUNCTION audit_log_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION
        'audit_log es append-only: operacion % no permitida sobre la tabla %',
        TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;

CREATE TRIGGER trg_audit_log_append_only
    BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW
    EXECUTE FUNCTION audit_log_append_only();
"""

# Reverse: elimina trigger y función para poder revertir la migración.
SQL_REVERTIR = r"""
DROP TRIGGER IF EXISTS trg_audit_log_append_only ON audit_log;
DROP FUNCTION IF EXISTS audit_log_append_only();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(
            sql=SQL_CREAR,
            reverse_sql=SQL_REVERTIR,
        ),
    ]
