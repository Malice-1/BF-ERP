from django.db import migrations


def install(apps, schema_editor):
    original = ("checksum", "business_key", "original_filename", "storage_path", "invoice_number", "issue_date",
        "due_date", "currency", "subtotal", "tax_total", "total", "payable", "extracted_data", "created_at")
    if schema_editor.connection.vendor == "sqlite":
        condition = " OR ".join(f'NEW."{field}" IS NOT OLD."{field}"' for field in original)
        fields = apps.get_model("accounting", "SupplierInvoice")._meta.fields
        frozen = " OR ".join(f'NEW."{f.column}" IS NOT OLD."{f.column}"' for f in fields if f.column not in ("created_by_id", "reviewed_by_id"))
        schema_editor.execute(f"""CREATE TRIGGER acct_supplier_original BEFORE UPDATE ON accounting_supplierinvoice
            WHEN ({condition}) OR (OLD.status<>'RECEIVED' AND ({frozen}))
            BEGIN SELECT RAISE(ABORT,'Supplier XML and completed reviews are immutable'); END""")
        schema_editor.execute("""CREATE TRIGGER acct_supplier_no_delete BEFORE DELETE ON accounting_supplierinvoice
            BEGIN SELECT RAISE(ABORT,'Supplier invoice history cannot be deleted'); END""")
        fields = apps.get_model("accounting", "SupplierInvoiceValidation")._meta.fields
        frozen = " OR ".join(f'NEW."{f.column}" IS NOT OLD."{f.column}"' for f in fields if f.column != "actor_id")
        schema_editor.execute(f"""CREATE TRIGGER acct_supplier_validation_update BEFORE UPDATE ON accounting_supplierinvoicevalidation
            WHEN ({frozen}) OR NEW.actor_id IS NOT NULL
            BEGIN SELECT RAISE(ABORT,'Supplier validation history is immutable'); END""")
        schema_editor.execute("""CREATE TRIGGER acct_supplier_validation_delete BEFORE DELETE ON accounting_supplierinvoicevalidation
            BEGIN SELECT RAISE(ABORT,'Supplier validation history is immutable'); END""")
    elif schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("""
        CREATE FUNCTION acct_supplier_xml_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Supplier invoice history cannot be deleted'; END IF;
          IF (to_jsonb(NEW)-ARRAY['supplier_id','status','revision','review_note','review_snapshot','reviewed_at','reviewed_by_id','reviewed_by_name','created_by_id'])
            IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['supplier_id','status','revision','review_note','review_snapshot','reviewed_at','reviewed_by_id','reviewed_by_name','created_by_id'])
          THEN RAISE EXCEPTION 'Imported supplier XML data is immutable'; END IF;
          IF OLD.status<>'RECEIVED' AND (to_jsonb(NEW)-ARRAY['created_by_id','reviewed_by_id'])
            IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['created_by_id','reviewed_by_id'])
          THEN RAISE EXCEPTION 'Completed supplier invoice reviews are immutable'; END IF;
          IF NEW.status NOT IN ('RECEIVED','REVIEWED','REJECTED') THEN RAISE EXCEPTION 'Invalid review status'; END IF;
          IF NEW.status='REVIEWED' AND (NEW.supplier_id IS NULL OR NEW.reviewed_at IS NULL OR btrim(NEW.review_note)=''
            OR NEW.review_snapshot='{}'::jsonb) THEN RAISE EXCEPTION 'Supplier review metadata required'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER acct_supplier_xml_guard BEFORE UPDATE OR DELETE ON accounting_supplierinvoice
          FOR EACH ROW EXECUTE FUNCTION acct_supplier_xml_guard();
        CREATE FUNCTION acct_supplier_validation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='UPDATE' AND NEW.actor_id IS NULL AND (to_jsonb(NEW)-'actor_id') IS NOT DISTINCT FROM (to_jsonb(OLD)-'actor_id')
          THEN RETURN NEW; END IF;
          RAISE EXCEPTION 'Supplier validation history is immutable';
        END $$;
        CREATE TRIGGER acct_supplier_validation_guard BEFORE UPDATE OR DELETE ON accounting_supplierinvoicevalidation
          FOR EACH ROW EXECUTE FUNCTION acct_supplier_validation_guard();
        """)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        for name in ("acct_supplier_original", "acct_supplier_no_delete", "acct_supplier_validation_update", "acct_supplier_validation_delete"):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif schema_editor.connection.vendor == "postgresql":
        for table, name in (("supplierinvoice", "acct_supplier_xml_guard"), ("supplierinvoicevalidation", "acct_supplier_validation_guard")):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON accounting_{table}")
            schema_editor.execute(f"DROP FUNCTION IF EXISTS {name}()")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0005_supplierinvoice_supplierinvoicevalidation")]
    operations = [migrations.RunPython(install, uninstall)]
