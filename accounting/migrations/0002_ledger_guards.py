from django.db import migrations


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        fields = apps.get_model("accounting", "JournalEntry")._meta.fields
        unchanged = " AND ".join(f'NEW."{f.column}" IS OLD."{f.column}"' for f in fields if f.column not in ("created_by_id", "posted_by_id"))
        schema_editor.execute(f"""CREATE TRIGGER acct_entry_immutable BEFORE UPDATE ON accounting_journalentry
            WHEN OLD.status='POSTED' AND NOT (({unchanged})
              AND (NEW.created_by_id IS OLD.created_by_id OR NEW.created_by_id IS NULL)
              AND (NEW.posted_by_id IS OLD.posted_by_id OR NEW.posted_by_id IS NULL))
            BEGIN SELECT RAISE(ABORT,'Posted entries are immutable'); END""")
        schema_editor.execute("""CREATE TRIGGER acct_entry_no_delete BEFORE DELETE ON accounting_journalentry
            BEGIN SELECT RAISE(ABORT,'Accounting history cannot be deleted'); END""")
        for operation in ("INSERT", "UPDATE", "DELETE"):
            row = "OLD" if operation == "DELETE" else "NEW"
            schema_editor.execute(f"""CREATE TRIGGER acct_line_{operation.lower()} BEFORE {operation} ON accounting_journalentryline
                WHEN (SELECT status FROM accounting_journalentry WHERE id={row}.entry_id)='POSTED'
                BEGIN SELECT RAISE(ABORT,'Posted lines are immutable'); END""")
        fields = apps.get_model("accounting", "AccountingEvent")._meta.fields
        unchanged = " AND ".join(f'NEW."{f.column}" IS OLD."{f.column}"' for f in fields if f.column != "actor_id")
        schema_editor.execute(f"""CREATE TRIGGER acct_audit_update BEFORE UPDATE ON accounting_accountingevent
            WHEN NOT (NEW.actor_id IS NULL AND ({unchanged}))
            BEGIN SELECT RAISE(ABORT,'Accounting audit is immutable'); END""")
        schema_editor.execute("""CREATE TRIGGER acct_audit_delete BEFORE DELETE ON accounting_accountingevent
            BEGIN SELECT RAISE(ABORT,'Accounting audit is immutable'); END""")
        return
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("""
    CREATE FUNCTION acct_reference_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM pg_advisory_xact_lock(77318401);
      PERFORM id FROM accounting_accountingprofile WHERE id=1 FOR UPDATE;
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Accounting references cannot be deleted'; END IF;
      IF TG_TABLE_NAME='accounting_fiscalyear' THEN
        IF EXISTS(SELECT 1 FROM accounting_fiscalyear WHERE id<>NEW.id
          AND start_date<=NEW.end_date AND end_date>=NEW.start_date) THEN
          RAISE EXCEPTION 'Overlapping fiscal years'; END IF;
        IF TG_OP='UPDATE' AND (NEW.code,NEW.start_date,NEW.end_date) IS DISTINCT FROM (OLD.code,OLD.start_date,OLD.end_date)
          AND EXISTS(SELECT 1 FROM accounting_accountingperiod WHERE fiscal_year_id=OLD.id)
        THEN RAISE EXCEPTION 'Used fiscal year boundaries are immutable'; END IF;
      ELSIF TG_TABLE_NAME='accounting_accountingperiod' THEN
        IF NOT EXISTS(SELECT 1 FROM accounting_fiscalyear WHERE id=NEW.fiscal_year_id
          AND start_date<=NEW.start_date AND end_date>=NEW.end_date) THEN
          RAISE EXCEPTION 'Period outside fiscal year'; END IF;
        IF EXISTS(SELECT 1 FROM accounting_accountingperiod WHERE id<>NEW.id AND fiscal_year_id=NEW.fiscal_year_id
          AND start_date<=NEW.end_date AND end_date>=NEW.start_date) THEN
          RAISE EXCEPTION 'Overlapping accounting periods'; END IF;
        IF TG_OP='UPDATE' AND (NEW.fiscal_year_id,NEW.start_date,NEW.end_date,NEW.label)
          IS DISTINCT FROM (OLD.fiscal_year_id,OLD.start_date,OLD.end_date,OLD.label)
          AND EXISTS(SELECT 1 FROM accounting_journalentry WHERE period_id=OLD.id)
        THEN RAISE EXCEPTION 'Used period boundaries are immutable'; END IF;
      ELSIF TG_TABLE_NAME='accounting_account' THEN
        IF TG_OP='UPDATE' AND (NEW.code,NEW.postable,NEW.party_requirement)
          IS DISTINCT FROM (OLD.code,OLD.postable,OLD.party_requirement) AND EXISTS(
          SELECT 1 FROM accounting_journalentryline WHERE account_id=OLD.id)
        THEN RAISE EXCEPTION 'Used account structure is immutable'; END IF;
        UPDATE accounting_accountingprofile SET approved_at=NULL, approved_by_id=NULL,
          approved_by_name='', revision=revision+1 WHERE id=1;
      ELSIF TG_TABLE_NAME='accounting_journal' THEN
        IF TG_OP='UPDATE' AND (NEW.code,NEW.kind) IS DISTINCT FROM (OLD.code,OLD.kind)
          AND EXISTS(SELECT 1 FROM accounting_journalentry WHERE journal_id=OLD.id)
        THEN RAISE EXCEPTION 'Used journal codes and kinds are immutable'; END IF;
      END IF;
      RETURN NEW;
    END $$;

    CREATE FUNCTION acct_line_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE parent_id bigint; parent_status text;
    BEGIN
      IF TG_OP='UPDATE' AND NEW.entry_id<>OLD.entry_id THEN RAISE EXCEPTION 'Cannot reparent an accounting line'; END IF;
      IF TG_OP='DELETE' THEN parent_id:=OLD.entry_id; ELSE parent_id:=NEW.entry_id; END IF;
      SELECT status INTO parent_status FROM accounting_journalentry WHERE id=parent_id FOR UPDATE;
      IF parent_status<>'DRAFT' THEN RAISE EXCEPTION 'Posted lines are immutable'; END IF;
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER acct_line_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalentryline
      FOR EACH ROW EXECUTE FUNCTION acct_line_guard();

    CREATE FUNCTION acct_entry_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE p accounting_accountingperiod%ROWTYPE; y accounting_fiscalyear%ROWTYPE;
      j accounting_journal%ROWTYPE; cfg accounting_accountingprofile%ROWTYPE;
      d numeric; c numeric; n integer;
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Accounting history cannot be deleted'; END IF;
      IF TG_OP='INSERT' THEN
        IF NEW.status<>'DRAFT' THEN RAISE EXCEPTION 'Entries must first be drafts'; END IF;
        RETURN NEW;
      END IF;
      IF OLD.status='POSTED' THEN
        IF (to_jsonb(NEW)-ARRAY['created_by_id','posted_by_id']) IS NOT DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['created_by_id','posted_by_id'])
          AND (NEW.created_by_id IS NOT DISTINCT FROM OLD.created_by_id OR NEW.created_by_id IS NULL)
          AND (NEW.posted_by_id IS NOT DISTINCT FROM OLD.posted_by_id OR NEW.posted_by_id IS NULL)
        THEN RETURN NEW; END IF;
        RAISE EXCEPTION 'Posted entries are immutable; reverse them';
      END IF;
      IF NEW.status='POSTED' THEN
        SELECT * INTO cfg FROM accounting_accountingprofile WHERE id=1 FOR UPDATE;
        IF cfg.approved_at IS NULL OR cfg.issuer_id IS NULL THEN RAISE EXCEPTION 'Chart approval required'; END IF;
        SELECT * INTO p FROM accounting_accountingperiod WHERE id=NEW.period_id FOR UPDATE;
        SELECT * INTO y FROM accounting_fiscalyear WHERE id=p.fiscal_year_id FOR UPDATE;
        SELECT * INTO j FROM accounting_journal WHERE id=NEW.journal_id FOR UPDATE;
        IF NOT p.is_open OR NOT y.is_open OR NOT j.is_active OR NEW.accounting_date<p.start_date
          OR NEW.accounting_date>p.end_date OR btrim(NEW.document_reference)='' THEN
          RAISE EXCEPTION 'Closed or invalid posting period/journal/document'; END IF;
        SELECT COUNT(*),COALESCE(SUM(debit),0),COALESCE(SUM(credit),0) INTO n,d,c
          FROM accounting_journalentryline WHERE entry_id=NEW.id;
        IF n<2 OR d<=0 OR d<>c OR NEW.debit_total<>d OR NEW.credit_total<>c THEN
          RAISE EXCEPTION 'Unbalanced accounting entry'; END IF;
        IF NEW.posted_by_id IS NULL OR btrim(NEW.posted_by_name)='' OR NEW.issuer_snapshot='{}'::jsonb
          OR NEW.journal_snapshot='{}'::jsonb OR NEW.fiscal_snapshot='{}'::jsonb THEN
          RAISE EXCEPTION 'Posting identity and snapshots required'; END IF;
        IF EXISTS(SELECT 1 FROM accounting_journalentryline l JOIN accounting_account a ON a.id=l.account_id
          WHERE l.entry_id=NEW.id AND (NOT a.postable OR (NOT a.is_active AND NEW.reversal_of_id IS NULL)
            OR (a.party_requirement='CUSTOMER' AND (l.customer_id IS NULL OR l.supplier_id IS NOT NULL))
            OR (a.party_requirement='SUPPLIER' AND (l.supplier_id IS NULL OR l.customer_id IS NOT NULL))
            OR l.account_snapshot='{}'::jsonb)) THEN RAISE EXCEPTION 'Invalid account or party'; END IF;
        IF NEW.reversal_of_id IS NOT NULL THEN
          IF NOT EXISTS(SELECT 1 FROM accounting_journalentry WHERE id=NEW.reversal_of_id AND status='POSTED'
            AND reversal_of_id IS NULL AND journal_id=NEW.journal_id AND accounting_date<=NEW.accounting_date)
          THEN RAISE EXCEPTION 'Invalid reversal origin'; END IF;
          IF n<>(SELECT COUNT(*) FROM accounting_journalentryline WHERE entry_id=NEW.reversal_of_id) OR EXISTS(
            SELECT 1 FROM accounting_journalentryline l LEFT JOIN accounting_journalentryline o
              ON o.entry_id=NEW.reversal_of_id AND o.position=l.position
            WHERE l.entry_id=NEW.id AND (o.id IS NULL OR
              (l.account_id,l.debit,l.credit,l.customer_id,l.supplier_id,l.account_snapshot,l.party_snapshot)
              IS DISTINCT FROM (o.account_id,o.credit,o.debit,o.customer_id,o.supplier_id,o.account_snapshot,o.party_snapshot)))
          THEN RAISE EXCEPTION 'Reversal lines must exactly invert original lines'; END IF;
        END IF;
        IF NOT EXISTS(SELECT 1 FROM accounting_entrysequence s WHERE s.journal_id=NEW.journal_id
          AND s.fiscal_year_id=y.id AND s.last_date=NEW.accounting_date
          AND NEW.number=j.code||'-'||y.code||'-'||lpad(s.last_number::text,GREATEST(length(s.last_number::text),6),'0'))
        THEN RAISE EXCEPTION 'Atomic journal sequence required'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER acct_entry_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalentry
      FOR EACH ROW EXECUTE FUNCTION acct_entry_guard();

    CREATE FUNCTION acct_audit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='UPDATE' AND NEW.actor_id IS NULL AND (to_jsonb(NEW)-'actor_id') IS NOT DISTINCT FROM (to_jsonb(OLD)-'actor_id')
      THEN RETURN NEW; END IF;
      RAISE EXCEPTION 'Accounting audit is immutable';
    END $$;
    CREATE TRIGGER acct_audit_guard BEFORE UPDATE OR DELETE ON accounting_accountingevent
      FOR EACH ROW EXECUTE FUNCTION acct_audit_guard();

    CREATE FUNCTION acct_sequence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Journal counters cannot be deleted'; END IF;
      IF NEW.journal_id<>OLD.journal_id OR NEW.fiscal_year_id<>OLD.fiscal_year_id OR NEW.last_number<>OLD.last_number+1
        OR NEW.last_date IS NULL OR (OLD.last_date IS NOT NULL AND NEW.last_date<OLD.last_date)
      THEN RAISE EXCEPTION 'Journal counters must advance once, in chronological order'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER acct_sequence_guard BEFORE UPDATE OR DELETE ON accounting_entrysequence
      FOR EACH ROW EXECUTE FUNCTION acct_sequence_guard();
    """, params=None)
    for table in ("fiscalyear", "accountingperiod", "account", "journal"):
        schema_editor.execute(f"CREATE TRIGGER acct_reference_guard BEFORE INSERT OR UPDATE OR DELETE ON accounting_{table} "
            "FOR EACH ROW EXECUTE FUNCTION acct_reference_guard()")


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor == "sqlite":
        for name in ("acct_entry_immutable", "acct_entry_no_delete", "acct_line_insert", "acct_line_update",
                     "acct_line_delete", "acct_audit_update", "acct_audit_delete"):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif schema_editor.connection.vendor == "postgresql":
        for table in ("fiscalyear", "accountingperiod", "account", "journal"):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS acct_reference_guard ON accounting_{table}")
        for table, function in (("journalentry", "acct_entry_guard"), ("journalentryline", "acct_line_guard"),
                ("accountingevent", "acct_audit_guard"), ("entrysequence", "acct_sequence_guard")):
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {function} ON accounting_{table}")
            schema_editor.execute(f"DROP FUNCTION IF EXISTS {function}()")
        schema_editor.execute("DROP FUNCTION IF EXISTS acct_reference_guard()")


class Migration(migrations.Migration):
    dependencies = [("accounting", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
