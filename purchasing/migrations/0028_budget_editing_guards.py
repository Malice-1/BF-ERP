from django.db import migrations


VERSION_EDIT_CHECK = """
            -- BF_ERP_BUDGET_EDIT_STATE
            IF TG_TABLE_NAME = 'purchasing_envelopeversion' AND TG_OP = 'UPDATE' THEN
                IF current_setting('bf_erp.budget_edit_state', true) = 'on' THEN
                    IF OLD.deleted_at IS NULL AND
                       (to_jsonb(NEW) - ARRAY['locked_at', 'editing_unlocked_at']) =
                       (to_jsonb(OLD) - ARRAY['locked_at', 'editing_unlocked_at']) THEN
                        RETURN NEW;
                    END IF;
                    RAISE EXCEPTION 'Only the budget editing state may be changed';
                END IF;
                IF NEW.editing_unlocked_at IS DISTINCT FROM OLD.editing_unlocked_at THEN
                    RAISE EXCEPTION 'Budget editing state requires an administrator transition';
                END IF;
            END IF;
"""

ALLOCATION_EDIT_CHECK = """
            -- BF_ERP_BUDGET_ALLOCATION_EDIT
            IF TG_TABLE_NAME = 'purchasing_allocation' THEN
                DECLARE budget_state jsonb;
                BEGIN
                    SELECT to_jsonb(v) INTO budget_state
                    FROM purchasing_envelopeversion v WHERE id = version;
                    IF budget_state->>'locked_at' IS NOT NULL OR budget_state->>'deleted_at' IS NOT NULL THEN
                        RAISE EXCEPTION 'Locked or deleted budget allocations are immutable';
                    END IF;
                    IF budget_state->>'editing_unlocked_at' IS NOT NULL THEN
                        published := NULL;
                    END IF;
                END;
            END IF;
"""


def change_guards(schema_editor, install):
    if schema_editor.connection.vendor != "postgresql":
        return
    for function, needle, addition in (
        ("erp_procurement_published_guard", "IF OLD.published_at IS NOT NULL THEN", VERSION_EDIT_CHECK),
        ("erp_procurement_child_guard", "IF published IS NOT NULL THEN", ALLOCATION_EDIT_CHECK),
    ):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SELECT pg_get_functiondef(%s::regproc)", [function])
            definition = cursor.fetchone()[0]
        if install:
            if needle not in definition:
                raise RuntimeError(f"Cannot extend the existing history guard: {function}")
            definition = definition.replace(needle, addition + needle, 1)
        else:
            definition = definition.replace(addition, "", 1)
        # Keep the existing maintenance and deleted-user exceptions intact.
        schema_editor.execute(definition, params=None)


def install(apps, schema_editor):
    change_guards(schema_editor, True)


def uninstall(apps, schema_editor):
    change_guards(schema_editor, False)


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0027_envelopeversion_editing_unlocked_at"),
        ("workflow", "0008_alter_activitylog_action_alter_auditevent_action_and_more"),
    ]
    operations = [migrations.RunPython(install, uninstall)]
