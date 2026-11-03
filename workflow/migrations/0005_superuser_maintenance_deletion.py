from django.db import migrations


ALLOW_MAINTENANCE = """
            -- BF_ERP_MAINTENANCE_DELETE
            IF TG_TABLE_NAME <> 'workflow_activitylog'
               AND current_setting('bf_erp.maintenance_delete', true) = 'on' THEN
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                IF TG_OP = 'UPDATE' THEN RETURN NEW; END IF;
            END IF;
"""


def change_guards(schema_editor, install):
    if schema_editor.connection.vendor != "postgresql":
        return
    for function in (
        "erp_procurement_published_guard", "erp_procurement_child_guard",
        "erp_procurement_history_guard", "erp_reject_authorization_version_mutation",
    ):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [function])
            definition = cursor.fetchone()[0]
        if install:
            definition = definition.replace("BEGIN", "BEGIN" + ALLOW_MAINTENANCE, 1)
        else:
            definition = definition.replace(ALLOW_MAINTENANCE, "")
        schema_editor.execute(definition, params=None)


def install(apps, schema_editor):
    change_guards(schema_editor, True)


def uninstall(apps, schema_editor):
    change_guards(schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [("workflow", "0004_independent_history")]
    operations = [migrations.RunPython(install, uninstall)]
