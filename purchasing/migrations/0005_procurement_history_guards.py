from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
        CREATE FUNCTION erp_procurement_published_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.published_at IS NOT NULL THEN
                IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Published version is immutable'; END IF;
                IF (to_jsonb(NEW) - 'active') IS DISTINCT FROM (to_jsonb(OLD) - 'active') THEN
                    RAISE EXCEPTION 'Published version is immutable';
                END IF;
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$
    """)
    for table in ("purchasing_workflowversion", "purchasing_envelopeversion"):
        schema_editor.execute(f"CREATE TRIGGER published_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION erp_procurement_published_guard()")
    schema_editor.execute("""
        CREATE FUNCTION erp_procurement_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE published timestamptz; version bigint;
        BEGIN
            IF TG_OP = 'INSERT' THEN version := NEW.version_id; ELSE version := OLD.version_id; END IF;
            EXECUTE format('SELECT published_at FROM %%I WHERE id = $1 FOR UPDATE', TG_ARGV[0]) INTO published USING version;
            IF published IS NOT NULL THEN RAISE EXCEPTION 'Published configuration rows are immutable'; END IF;
            IF TG_OP = 'UPDATE' AND OLD.version_id IS DISTINCT FROM NEW.version_id THEN
                RAISE EXCEPTION 'Cannot move a configuration row';
            END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$
    """)
    for table, parent in (("purchasing_approvalrule", "purchasing_workflowversion"), ("purchasing_allocation", "purchasing_envelopeversion")):
        schema_editor.execute(f"CREATE TRIGGER child_guard BEFORE INSERT OR UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION erp_procurement_child_guard('{parent}')")
    schema_editor.execute("""
        CREATE FUNCTION erp_procurement_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'purchasing_linesnapshot' THEN
                IF (to_jsonb(NEW) - 'line_id') = (to_jsonb(OLD) - 'line_id') AND NEW.line_id IS NULL THEN RETURN NEW; END IF;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'purchasing_submission' THEN
                IF (to_jsonb(NEW) - 'active') = (to_jsonb(OLD) - 'active') AND OLD.active AND NOT NEW.active THEN RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'Procurement history is immutable';
        END $$
    """)
    for table in ("purchasing_linesnapshot", "purchasing_submission", "purchasing_purchaseorder", "workflow_auditevent", "workflow_configurationauditevent"):
        schema_editor.execute(f"CREATE TRIGGER history_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION erp_procurement_history_guard()")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("purchasing_linesnapshot", "purchasing_submission", "purchasing_purchaseorder", "workflow_auditevent", "workflow_configurationauditevent"):
        schema_editor.execute(f"DROP TRIGGER history_guard ON {table}")
    for table in ("purchasing_approvalrule", "purchasing_allocation"):
        schema_editor.execute(f"DROP TRIGGER child_guard ON {table}")
    for table in ("purchasing_workflowversion", "purchasing_envelopeversion"):
        schema_editor.execute(f"DROP TRIGGER published_guard ON {table}")
    schema_editor.execute("DROP FUNCTION erp_procurement_history_guard()")
    schema_editor.execute("DROP FUNCTION erp_procurement_child_guard()")
    schema_editor.execute("DROP FUNCTION erp_procurement_published_guard()")


class Migration(migrations.Migration):
    dependencies = [("purchasing", "0004_annualenvelope_envelopeversion_and_more"), ("workflow", "0002_configurationauditevent")]
    operations = [migrations.RunPython(install, uninstall)]
