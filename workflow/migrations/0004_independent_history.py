from django.db import migrations


def migrate_history(apps, schema_editor):
    alias = schema_editor.connection.alias
    postgres = schema_editor.connection.vendor == "postgresql"
    Log = apps.get_model("workflow", "ActivityLog")
    if postgres:
        schema_editor.execute("DROP TRIGGER child_guard ON purchasing_approvalrule")
        schema_editor.execute("ALTER TABLE budgeting_costcentermanagerassignment DROP CONSTRAINT manager_no_overlapping_periods")
        schema_editor.execute("""
            ALTER TABLE budgeting_costcentermanagerassignment ADD CONSTRAINT manager_no_overlapping_periods
            EXCLUDE USING gist (cost_center_id WITH =, tstzrange(valid_from, valid_until, '[)') WITH &&)
            WHERE (user_id IS NOT NULL)
        """)

    Rule = apps.get_model("purchasing", "ApprovalRule")
    for rule in Rule.objects.using(alias).filter(named_user__isnull=False).select_related("named_user").iterator():
        Rule.objects.using(alias).filter(pk=rule.pk).update(
            named_user_reference=f"{rule.named_user_id}: {rule.named_user.username}")

    for name in ("AuditEvent", "ConfigurationAuditEvent"):
        Model = apps.get_model("workflow", name)
        for event in Model.objects.using(alias).select_related("actor").iterator():
            user_event = event.actor_id is not None and event.payload.get("origin") != "system"
            details = {"payload": event.payload}
            if name == "AuditEvent":
                details.update(purchase_request_id=event.purchase_request_id, revision=event.revision)
            else:
                details.update(object_type=event.object_type, object_id=event.object_id)
            Log.objects.using(alias).get_or_create(
                source=f"{Model._meta.label_lower}:{event.pk}",
                defaults=dict(created_at=event.created_at,
                              actor_identifier=str(event.actor_id) if user_event else "system",
                              actor_username=event.actor.username if user_event else "Système",
                              action=event.action, object_type=Model._meta.label_lower,
                              object_identifier=str(event.pk), details=details))

    # Also preserve pre-existing actions performed through Django admin.
    AdminLog = apps.get_model("admin", "LogEntry")
    for event in AdminLog.objects.using(alias).select_related("user", "content_type").iterator():
        Log.objects.using(alias).get_or_create(source=f"admin.logentry:{event.pk}", defaults=dict(
            created_at=event.action_time, actor_identifier=str(event.user_id), actor_username=event.user.username,
            action={1: "admin.created", 2: "admin.updated", 3: "admin.deleted"}.get(event.action_flag, "admin.action"),
            object_type=f"{event.content_type.app_label}.{event.content_type.model}" if event.content_type else "unknown",
            object_identifier=event.object_id or "", details={"label": event.object_repr, "message": event.change_message}))

    if postgres:
        schema_editor.execute("""
        CREATE OR REPLACE FUNCTION erp_procurement_child_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE published timestamptz; version bigint;
        BEGIN
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'purchasing_approvalrule' THEN
                IF OLD.named_user_id IS NOT NULL AND NEW.named_user_id IS NULL
                   AND (to_jsonb(NEW) - 'named_user_id') = (to_jsonb(OLD) - 'named_user_id') THEN RETURN NEW; END IF;
            END IF;
            IF TG_OP = 'INSERT' THEN version := NEW.version_id; ELSE version := OLD.version_id; END IF;
            EXECUTE format('SELECT published_at FROM %%I WHERE id = $1 FOR UPDATE', TG_ARGV[0]) INTO published USING version;
            IF published IS NOT NULL THEN RAISE EXCEPTION 'Published configuration rows are immutable'; END IF;
            IF TG_OP = 'UPDATE' AND OLD.version_id IS DISTINCT FROM NEW.version_id THEN RAISE EXCEPTION 'Cannot move a configuration row'; END IF;
            IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$
        """)
        schema_editor.execute("CREATE TRIGGER child_guard BEFORE INSERT OR UPDATE OR DELETE ON purchasing_approvalrule FOR EACH ROW EXECUTE FUNCTION erp_procurement_child_guard('purchasing_workflowversion')")
        schema_editor.execute("""
        CREATE OR REPLACE FUNCTION erp_reject_authorization_version_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND OLD.created_by_id IS NOT NULL AND NEW.created_by_id IS NULL
               AND (to_jsonb(NEW) - 'created_by_id') = (to_jsonb(OLD) - 'created_by_id') THEN RETURN NEW; END IF;
            RAISE EXCEPTION 'Authorization versions are immutable';
        END $$
        """)
        schema_editor.execute("""
        CREATE OR REPLACE FUNCTION erp_procurement_history_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME IN ('workflow_auditevent', 'workflow_configurationauditevent') THEN
                IF OLD.actor_id IS NOT NULL AND NEW.actor_id IS NULL AND (to_jsonb(NEW) - 'actor_id') = (to_jsonb(OLD) - 'actor_id') THEN RETURN NEW; END IF;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'purchasing_linesnapshot' THEN
                IF (to_jsonb(NEW) - 'line_id') = (to_jsonb(OLD) - 'line_id') AND NEW.line_id IS NULL THEN RETURN NEW; END IF;
            END IF;
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'purchasing_submission' THEN
                IF (to_jsonb(NEW) - 'active') = (to_jsonb(OLD) - 'active') AND OLD.active AND NOT NEW.active THEN RETURN NEW; END IF;
            END IF;
            RAISE EXCEPTION 'Procurement history is immutable';
        END $$
        """)
        schema_editor.execute("CREATE TRIGGER activity_immutable BEFORE UPDATE OR DELETE ON workflow_activitylog FOR EACH ROW EXECUTE FUNCTION erp_procurement_history_guard()")
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(f"CREATE TRIGGER activity_no_{operation.lower()} BEFORE {operation} ON workflow_activitylog BEGIN SELECT RAISE(ABORT, 'Activity log is immutable'); END")


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0003_activitylog_alter_auditevent_actor_and_more"),
        ("accounts", "0006_alter_authorization_user_and_more"),
        ("budgeting", "0010_alter_costcentermanagerassignment_user"),
        ("purchasing", "0011_approvalrule_named_user_reference"),
        ("admin", "0003_logentry_add_action_flag_choices"),
    ]
    operations = [migrations.RunPython(migrate_history)]
