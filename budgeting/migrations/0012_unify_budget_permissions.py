from django.db import migrations


def transfer(apps, schema_editor):
    alias = schema_editor.connection.alias
    CT = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    relations = [
        (apps.get_model("accounts", "User").user_permissions.through, "user"),
        (apps.get_model("accounts", "Role").permissions.through, "role"),
        (apps.get_model("auth", "Group").permissions.through, "group"),
    ]

    def move(old_app, old_model, action, targets):
        old = Permission.objects.using(alias).filter(
            content_type__app_label=old_app, content_type__model=old_model,
            codename=f"{action}_{old_model}").first()
        for model in targets:
            ct, _ = CT.objects.using(alias).get_or_create(app_label="budgeting", model=model)
            new, _ = Permission.objects.using(alias).get_or_create(
                content_type=ct, codename=f"{action}_{model}", defaults={"name": f"{action}_{model}"})
            if old:
                for through, owner in relations:
                    keys = through.objects.using(alias).filter(permission_id=old.pk).values_list(f"{owner}_id", flat=True)
                    for key in keys:
                        through.objects.using(alias).get_or_create(**{f"{owner}_id": key, "permission_id": new.pk})
        if old:
            old.delete(using=alias)

    for action in ("add", "change", "delete", "view"):
        for model in ("annualenvelope", "envelopeversion", "allocation", "budgetentry"):
            move("purchasing", model, action, [model])
        # Retire the inactive legacy budget permissions without losing grants.
        move("budgeting", "budget", action,
             ["annualenvelope", "envelopeversion"] if action in ("add", "view", "delete") else ["envelopeversion"])
        move("budgeting", "budgetline", action, ["allocation"])

    # Keep existing financial readers' access to balances, while making this
    # budget permission independent from access to purchase amounts.
    ct, _ = CT.objects.using(alias).get_or_create(app_label="budgeting", model="annualenvelope")
    balances, _ = Permission.objects.using(alias).get_or_create(content_type=ct,
        codename="view_budget_balances", defaults={"name": "Consulter les disponibilités budgétaires"})
    financial = Permission.objects.using(alias).filter(content_type__app_label="purchasing",
                                                     codename="view_purchase_financial").first()
    if financial:
        for through, owner in relations:
            for key in through.objects.using(alias).filter(permission_id=financial.pk).values_list(f"{owner}_id", flat=True):
                through.objects.using(alias).get_or_create(**{f"{owner}_id": key, "permission_id": balances.pk})


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0011_allocation_annualenvelope_budgetentry_and_more"),
        ("accounts", "0006_alter_authorization_user_and_more"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("workflow", "0005_superuser_maintenance_deletion"),
    ]
    operations = [migrations.RunPython(transfer)]
