from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION erp_reject_authorization_version_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Authorization versions are immutable';
        END $$
    """)
    schema_editor.execute("""
        CREATE TRIGGER authorization_version_immutable
        BEFORE UPDATE OR DELETE ON accounts_authorizationversion
        FOR EACH ROW EXECUTE FUNCTION erp_reject_authorization_version_mutation()
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER authorization_version_immutable ON accounts_authorizationversion")
        schema_editor.execute("DROP FUNCTION erp_reject_authorization_version_mutation()")


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_validationfunction_authorization_and_more")]
    operations = [migrations.RunPython(install, uninstall)]
