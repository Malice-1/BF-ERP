"""Protect issued fiscal history even against bulk SQL updates on PostgreSQL."""
from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
    CREATE FUNCTION sales_invoice_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Issued invoices cannot be deleted'; END IF;
      IF OLD.sealed AND (
        (to_jsonb(NEW) - ARRAY['document_status','document_error','payment_status'])
        IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['document_status','document_error','payment_status'])
      ) THEN RAISE EXCEPTION 'Issued commercial and fiscal data is immutable'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sales_invoice_guard BEFORE UPDATE OR DELETE ON sales_salesinvoice
      FOR EACH ROW EXECUTE FUNCTION sales_invoice_guard();

    CREATE FUNCTION sales_invoice_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE frozen boolean;
    BEGIN
      IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Invoice lines are immutable'; END IF;
      SELECT sealed INTO frozen FROM sales_salesinvoice WHERE id=NEW.invoice_id FOR UPDATE;
      IF frozen THEN RAISE EXCEPTION 'Cannot append lines to an issued invoice'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sales_invoice_line_guard BEFORE INSERT OR UPDATE OR DELETE ON sales_salesinvoiceline
      FOR EACH ROW EXECUTE FUNCTION sales_invoice_line_guard();

    CREATE FUNCTION sales_order_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Sales orders must be cancelled, not deleted'; END IF;
      IF OLD.status <> 'DRAFT' AND (
        (to_jsonb(NEW) - ARRAY['status','revision','updated_at','created_by_id']) IS DISTINCT FROM
        (to_jsonb(OLD) - ARRAY['status','revision','updated_at','created_by_id'])
      ) THEN RAISE EXCEPTION 'Confirmed commercial data is immutable'; END IF;
      IF NEW.status <> OLD.status AND NOT (
        (OLD.status='DRAFT' AND NEW.status IN ('CONFIRMED','CANCELLED')) OR
        (OLD.status='CONFIRMED' AND NEW.status IN ('INVOICED','CANCELLED'))
      ) THEN RAISE EXCEPTION 'Invalid sales order transition'; END IF;
      IF NEW.status='INVOICED' AND NOT EXISTS (
        SELECT 1 FROM sales_salesinvoice WHERE order_id=NEW.id AND sealed
      ) THEN RAISE EXCEPTION 'Invoiced orders require an issued invoice'; END IF;
      IF NEW.status='CANCELLED' AND EXISTS (
        SELECT 1 FROM sales_salesinvoice WHERE order_id=NEW.id
      ) THEN RAISE EXCEPTION 'Cannot cancel an invoiced order'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sales_order_guard BEFORE UPDATE OR DELETE ON sales_salesorder
      FOR EACH ROW EXECUTE FUNCTION sales_order_guard();

    CREATE FUNCTION sales_order_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_id bigint; parent_status text;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.order_id<>OLD.order_id THEN
        RAISE EXCEPTION 'Cannot reparent an order line';
      END IF;
      IF TG_OP='DELETE' THEN parent_id:=OLD.order_id; ELSE parent_id:=NEW.order_id; END IF;
      SELECT status INTO parent_status FROM sales_salesorder WHERE id=parent_id FOR UPDATE;
      IF parent_status<>'DRAFT' THEN RAISE EXCEPTION 'Only draft order lines can change'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER sales_order_line_guard BEFORE INSERT OR UPDATE OR DELETE ON sales_salesorderline
      FOR EACH ROW EXECUTE FUNCTION sales_order_line_guard();

    CREATE FUNCTION sales_append_only_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' AND TG_ARGV[0]<>'' THEN
        IF (to_jsonb(NEW)->TG_ARGV[0])='null'::jsonb AND
          (to_jsonb(NEW)-TG_ARGV[0]) IS NOT DISTINCT FROM (to_jsonb(OLD)-TG_ARGV[0])
        THEN RETURN NEW; END IF;
      END IF;
      RAISE EXCEPTION 'Sales history is append only';
    END $$;
    """)
    for table, actor in (("sales_invoicedocument", ""), ("sales_invoicevalidationrun", ""),
            ("sales_invoicepayment", "created_by_id"), ("sales_paymentreversal", "created_by_id"),
            ("sales_salesevent", "actor_id")):
        schema_editor.execute(f"CREATE TRIGGER sales_append_only BEFORE UPDATE OR DELETE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION sales_append_only_guard('{actor}')")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table in ("sales_invoicedocument", "sales_invoicevalidationrun", "sales_invoicepayment", "sales_paymentreversal", "sales_salesevent"):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS sales_append_only ON {table}")
    for table, name in (("sales_salesinvoice", "sales_invoice_guard"), ("sales_salesinvoiceline", "sales_invoice_line_guard"),
            ("sales_salesorder", "sales_order_guard"), ("sales_salesorderline", "sales_order_line_guard")):
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {name} ON {table}")
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {name}()")
    schema_editor.execute("DROP FUNCTION IF EXISTS sales_append_only_guard()")


class Migration(migrations.Migration):
    dependencies = [("sales", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
