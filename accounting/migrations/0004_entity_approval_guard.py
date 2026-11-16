from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
    CREATE FUNCTION acct_entity_approval_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.status='POSTED' AND OLD.status='DRAFT' THEN
        PERFORM id FROM accounting_accountingprofile WHERE id=1 FOR UPDATE;
        PERFORM issuer.id FROM sales_issuerconfiguration issuer
          JOIN accounting_accountingprofile cfg ON cfg.issuer_id=issuer.id
          WHERE cfg.id=1 FOR UPDATE OF issuer;
        IF NOT EXISTS(SELECT 1 FROM accounting_accountingprofile cfg
          JOIN sales_issuerconfiguration issuer ON issuer.id=cfg.issuer_id
          WHERE cfg.id=1 AND cfg.approved_at IS NOT NULL
          AND cfg.approved_issuer_snapshot=jsonb_build_object('name',issuer.name,'legal_id',issuer.legal_id,'country',issuer.country))
        THEN RAISE EXCEPTION 'Current entity identity requires accounting approval'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER acct_entity_approval_guard BEFORE UPDATE ON accounting_journalentry
      FOR EACH ROW EXECUTE FUNCTION acct_entity_approval_guard();
    """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("DROP TRIGGER IF EXISTS acct_entity_approval_guard ON accounting_journalentry")
        schema_editor.execute("DROP FUNCTION IF EXISTS acct_entity_approval_guard()")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0003_accountingprofile_approved_issuer_snapshot")]
    operations = [migrations.RunPython(install, uninstall)]
