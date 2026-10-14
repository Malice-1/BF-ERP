from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    schema_editor.execute("""
        ALTER TABLE budgeting_costcentermanagerassignment
        ADD CONSTRAINT manager_no_overlapping_periods
        EXCLUDE USING gist (
            cost_center_id WITH =,
            tstzrange(valid_from, valid_until, '[)') WITH &&
        )
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("ALTER TABLE budgeting_costcentermanagerassignment DROP CONSTRAINT manager_no_overlapping_periods")


class Migration(migrations.Migration):
    dependencies = [("budgeting", "0008_costcentermanagerassignment")]
    operations = [migrations.RunPython(install, uninstall)]
