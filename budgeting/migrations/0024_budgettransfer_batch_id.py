import uuid
from django.db import migrations, models


def initialize_batches(apps, schema_editor):
    Transfer = apps.get_model("budgeting", "BudgetTransfer")
    rows = Transfer.objects.using(schema_editor.connection.alias)
    for pk in rows.values_list("pk", flat=True).iterator():
        rows.filter(pk=pk).update(batch_id=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [("budgeting", "0023_alter_budgettransfer_options")]
    operations = [
        migrations.AddField(
            model_name="budgettransfer", name="batch_id",
            field=models.UUIDField(null=True, editable=False, db_index=True),
        ),
        migrations.RunPython(initialize_batches, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="budgettransfer", name="batch_id",
            field=models.UUIDField(default=uuid.uuid4, editable=False, db_index=True),
        ),
    ]
