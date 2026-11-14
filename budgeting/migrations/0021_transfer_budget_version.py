import django.db.models.deletion
from django.db import migrations, models


def assign_versions(apps, schema_editor):
    Transfer = apps.get_model("budgeting", "BudgetTransfer")
    Envelope = apps.get_model("purchasing", "AnnualEnvelope")
    Version = apps.get_model("purchasing", "EnvelopeVersion")
    alias = schema_editor.connection.alias
    for envelope_id in Transfer.objects.using(alias).values_list("envelope_id", flat=True).distinct():
        envelope = Envelope.objects.using(alias).get(pk=envelope_id)
        version_id = envelope.active_version_id
        if version_id is None:
            candidates = list(Version.objects.using(alias).filter(envelope_id=envelope_id).values_list("pk", flat=True))
            if len(candidates) != 1:
                raise RuntimeError(f"Les transferts de l’enveloppe {envelope.year} doivent être rattachés à une version avant migration : aucune version unique ne peut être déterminée.")
            version_id = candidates[0]
        Transfer.objects.using(alias).filter(envelope_id=envelope_id).update(budget_version_id=version_id)


class Migration(migrations.Migration):
    dependencies = [
        ("budgeting", "0020_alter_budgettransfer_options_budgethistoryevent"),
        ("purchasing", "0024_envelopeversion_deleted_at"),
    ]

    operations = [
        migrations.AddField(model_name="budgethistoryevent", name="version_id", field=models.PositiveBigIntegerField(blank=True, editable=False, null=True)),
        migrations.AddField(model_name="budgettransfer", name="budget_version", field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="purchasing.envelopeversion", verbose_name="Version budgétaire")),
        migrations.RunPython(assign_versions, migrations.RunPython.noop),
        migrations.AlterField(model_name="budgettransfer", name="budget_version", field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="purchasing.envelopeversion", verbose_name="Version budgétaire")),
    ]
