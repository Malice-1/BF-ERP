from django.db import migrations


def transfer(apps, schema_editor):
    alias = schema_editor.connection.alias
    CT = apps.get_model("contenttypes", "ContentType")
    Permission = apps.get_model("auth", "Permission")
    target_ct, _ = CT.objects.using(alias).get_or_create(app_label="purchasing", model="detailedproduct")
    relations = [
        (apps.get_model("accounts", "User").user_permissions.through, "user"),
        (apps.get_model("accounts", "Role").permissions.through, "role"),
        (apps.get_model("auth", "Group").permissions.through, "group"),
    ]
    for action, label in (("add", "Ajouter"), ("change", "Modifier"), ("delete", "Supprimer"), ("view", "Consulter")):
        codename = f"{action}_detailedproduct"
        old = Permission.objects.using(alias).filter(content_type__app_label="budgeting",
            content_type__model="detailedproduct", codename=codename).first()
        new, _ = Permission.objects.using(alias).get_or_create(content_type=target_ct,
            codename=codename, defaults={"name": f"{label} : produit détaillé"})
        if old:
            for through, owner in relations:
                for key in through.objects.using(alias).filter(permission_id=old.pk).values_list(f"{owner}_id", flat=True):
                    through.objects.using(alias).get_or_create(**{f"{owner}_id": key, "permission_id": new.pk})
            old.delete(using=alias)


class Migration(migrations.Migration):
    dependencies = [
        ("purchasing", "0013_detailedproduct"),
        ("budgeting", "0013_alter_detailedproduct_options"),
        ("accounts", "0006_alter_authorization_user_and_more"),
    ]
    operations = [migrations.RunPython(transfer)]
