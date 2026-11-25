from django.db import models
import uuid
from django.utils import timezone

class CostCenter(models.Model):
    managers = models.ManyToManyField("accounts.User", blank=True, related_name="managed_cost_centers", verbose_name="Responsables")
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    label = models.CharField(
        max_length=150,
        verbose_name='Libellé',
    )

    class Meta:
        verbose_name = 'CDF'
        verbose_name_plural = 'CDF'
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class Support(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Libellé")
    managers = models.ManyToManyField("accounts.User", blank=True,
        related_name="managed_supports", verbose_name="Responsables")

    class Meta:
        verbose_name = "support"
        verbose_name_plural = "supports"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class Funding(models.Model):
    managers = models.ManyToManyField("accounts.User", blank=True, related_name="managed_fundings", verbose_name="Responsables")
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    label = models.CharField(
        max_length=150,
        verbose_name='Libellé',
    )

    class Meta:
        verbose_name = 'financement'
        verbose_name_plural = 'financements'
        ordering = ["code"]

    def __str__(self):
        return self.code


class Subproject(models.Model):
    code = models.CharField("Code", max_length=50, unique=True)
    label = models.CharField("Libellé", max_length=150)

    class Meta:
        ordering = ["code"]
        verbose_name = "sous-projet"
        verbose_name_plural = "sous-projets"

    def __str__(self):
        return f"{self.code} - {self.label}"


class Section(models.Model):
    code = models.CharField("Code", max_length=50, unique=True)
    label = models.CharField("Libellé", max_length=150)

    class Meta:
        ordering = ["code"]
        verbose_name = "section"
        verbose_name_plural = "sections"

    def __str__(self):
        return f"{self.code} - {self.label}"


class BudgetProduct(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    label = models.CharField(
        max_length=150,
        verbose_name='Libellé',
    )

    class Meta:
        verbose_name = 'produit budgétaire (BI)'
        verbose_name_plural = 'produits budgétaires (BI)'
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class Budget(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    year = models.IntegerField(verbose_name='Année')

    is_active = models.BooleanField(
        default=False,
        verbose_name='Actif',
    )

    class Meta:
        default_permissions = ()
        verbose_name = "budget historique"
        verbose_name_plural = "budgets historiques"
        ordering = ["-year", "code"]

    def __str__(self):
        return f"{self.code} ({self.year})"


    def save(self, *args, **kwargs):

        if self.is_active:
            Budget.objects.exclude(pk=self.pk).update(
                is_active=False
            )

        super().save(*args, **kwargs)


class BudgetLine(models.Model):
    budget = models.ForeignKey(
        Budget,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name='Budget',
    )

    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="budget_lines",
        verbose_name='CDF',
    )

    funding = models.ForeignKey(
        Funding,
        on_delete=models.PROTECT,
        related_name="budget_lines",
        verbose_name='Financement',
    )

    budget_product = models.ForeignKey(
        BudgetProduct,
        on_delete=models.PROTECT,
        related_name="budget_lines",
        verbose_name='Produit budgétaire (BI)',
    )

    allocated_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Montant alloué',
    )

    committed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Montant engagé',
    )

    consumed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name='Montant consommé',
    )

    @property
    def available_amount(self):
        return (
            self.allocated_amount
            - self.committed_amount
            - self.consumed_amount
        )

    class Meta:
        default_permissions = ()
        verbose_name = "ligne de budget historique"
        verbose_name_plural = "lignes de budget historiques"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "budget",
                    "cost_center",
                    "funding",
                    "budget_product",
                ],
                name="unique_budget_line"
            )
        ]

    def __str__(self):
        return (
            f"{self.budget} - "
            f"{self.budget_product}"
        )


class DetailedProduct(models.Model):

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    label = models.CharField(
        max_length=255,
        verbose_name='Libellé',
    )

    budget_product = models.ForeignKey(
        "BudgetProduct",
        on_delete=models.PROTECT,
        related_name="detailed_products",
        verbose_name='Produit budgétaire (BI)',
    )

    class Meta:
        default_permissions = ()
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class CostCenterManagerAssignment(models.Model):
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, related_name="manager_assignments", verbose_name='CDF')
    user = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Utilisateur')
    valid_from = models.DateTimeField(verbose_name='Début de validité')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='Fin de validité')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')

    class Meta:
        verbose_name = 'affectation historique de responsable CDF'
        verbose_name_plural = 'affectations historiques de responsables CDF'
        ordering = ["valid_from", "pk"]
        permissions = [("manage_cost_center_managers", "Gérer les responsables CDF")]
        constraints = [
            models.CheckConstraint(condition=models.Q(valid_until__isnull=True) | models.Q(valid_until__gt=models.F("valid_from")), name="manager_valid_period"),
        ]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"

# Permission and administration models for the current budget workflow.
# Proxies share existing tables, preserving their data and SQL protections.
from purchasing.flow_models import (
    AnnualEnvelope as PurchaseAnnualEnvelope,
    EnvelopeVersion as PurchaseEnvelopeVersion,
    Allocation as PurchaseAllocation,
    BudgetEntry as PurchaseBudgetEntry,
)


class AnnualEnvelope(PurchaseAnnualEnvelope):
    class Meta:
        proxy = True
        default_permissions = ('add', 'change', 'delete', 'view')
        verbose_name = 'enveloppe budgétaire annuelle'
        verbose_name_plural = 'enveloppes budgétaires annuelles'
        permissions = [('view_budget_balances', 'Consulter les disponibilités budgétaires')]


class EnvelopeVersion(PurchaseEnvelopeVersion):
    class Meta:
        proxy = True
        default_permissions = ('add', 'change', 'delete', 'view')
        verbose_name = 'version budgétaire'
        verbose_name_plural = 'versions budgétaires'


class Allocation(PurchaseAllocation):
    class Meta:
        proxy = True
        default_permissions = ('add', 'change', 'delete', 'view')
        verbose_name = 'allocation budgétaire TVAC'
        verbose_name_plural = 'allocations budgétaires TVAC'


class BudgetEntry(PurchaseBudgetEntry):
    class Meta:
        proxy = True
        default_permissions = ('add', 'change', 'delete', 'view')
        verbose_name = 'écriture budgétaire'
        verbose_name_plural = 'écritures budgétaires'


class TransferConfiguration(models.Model):
    """Legacy configuration retained as data; transfers no longer consult it."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    envelope = models.ForeignKey(PurchaseAnnualEnvelope, on_delete=models.PROTECT, verbose_name="Enveloppe annuelle des transferts")
    users = models.ManyToManyField("accounts.User", blank=True, verbose_name="Utilisateurs autorisés", help_text="Ces utilisateurs peuvent créer et soumettre des transferts sur cette enveloppe, avec le droit de création de transferts.")

    class Meta:
        verbose_name = "configuration des transferts budgétaires"
        verbose_name_plural = "configuration des transferts budgétaires"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="single_transfer_configuration")]

    def __str__(self):
        return f"Transferts · {self.envelope}"


class BudgetTransferBatch(models.Model):
    key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    class Meta:
        default_permissions = ()
        verbose_name = "transfert général"
        verbose_name_plural = "transferts généraux"


class BudgetTransfer(models.Model):
    batch_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    budget_version = models.ForeignKey(PurchaseEnvelopeVersion, on_delete=models.PROTECT, related_name="transfers", verbose_name="Version budgétaire")
    envelope = models.ForeignKey(PurchaseAnnualEnvelope, on_delete=models.PROTECT, verbose_name="Enveloppe annuelle")
    source_cdf = models.ForeignKey(CostCenter, on_delete=models.PROTECT, related_name="outgoing_transfers", verbose_name="CDF source")
    source_funding = models.ForeignKey(Funding, on_delete=models.PROTECT, related_name="outgoing_transfers", verbose_name="Financement source")
    source_product = models.ForeignKey(BudgetProduct, on_delete=models.PROTECT, related_name="outgoing_transfers", verbose_name="BI source")
    destination_cdf = models.ForeignKey(CostCenter, on_delete=models.PROTECT, related_name="incoming_transfers", verbose_name="CDF destination")
    destination_funding = models.ForeignKey(Funding, on_delete=models.PROTECT, related_name="incoming_transfers", verbose_name="Financement destination")
    destination_product = models.ForeignKey(BudgetProduct, on_delete=models.PROTECT, related_name="incoming_transfers", verbose_name="BI destination")
    support = models.ForeignKey(Support, null=True, blank=True, on_delete=models.PROTECT, verbose_name="Support demandeur")
    source_support = models.ForeignKey(Support, null=True, blank=True, on_delete=models.PROTECT, related_name="outgoing_transfers", verbose_name="Support source")
    destination_support = models.ForeignKey(Support, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_transfers", verbose_name="Support destination")
    amount = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Montant TVAC")
    reason = models.TextField(verbose_name="Justification")
    created_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, verbose_name="Demandeur")
    created_at = models.DateTimeField(auto_now_add=True)
    workflow = models.ForeignKey("purchasing.WorkflowVersion", null=True, blank=True, on_delete=models.PROTECT)
    status = models.CharField(max_length=12, default="draft", choices=[("draft", "Brouillon"), ("pending", "En validation"), ("approved", "Approuvé"), ("rejected", "Rejeté"), ("returned", "À corriger"), ("cancelled", "Annulé")])
    return_reason = models.TextField(blank=True, verbose_name="Motif du retour au demandeur")
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "transfert budgétaire"
        verbose_name_plural = "transferts budgétaires"
        permissions = [("view_all_transfers", "Consulter tous les transferts budgétaires"),
                       ("cancel_any_budgettransfer", "Annuler les transferts budgétaires, y compris approuvés"),
                       ("decide_any_budgettransfer", "Valider ou refuser tout transfert budgétaire")]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="transfer_positive_amount")]

    def combination(self, side):
        return tuple(getattr(self, f"{side}_{field}_id") for field in ("cdf", "funding", "product"))

    def clean(self):
        super().clean()
        if self.budget_version_id:
            if self.envelope_id and self.envelope_id != self.budget_version.envelope_id:
                from django.core.exceptions import ValidationError
                raise ValidationError("La version budgétaire ne correspond pas à l’année du transfert.")
            self.envelope_id = self.budget_version.envelope_id

    def save(self, *args, **kwargs):
        self.clean()
        BudgetTransferBatch.objects.get_or_create(key=self.batch_id)
        if not self._state.adding:
            previous = type(self).objects.only("budget_version_id").get(pk=self.pk)
            if previous.budget_version_id != self.budget_version_id:
                from django.core.exceptions import ValidationError
                raise ValidationError("La version d’un transfert existant ne peut pas être changée.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"TB-{self.pk}"


class TrainingActivity(models.Model):
    training = models.ForeignKey("sales.TrainingService", on_delete=models.PROTECT, verbose_name="Formation")
    cost_center = models.ForeignKey(CostCenter, on_delete=models.PROTECT, verbose_name="CDF")
    month = models.DateField("Mois (premier jour)")
    trainees = models.PositiveIntegerField("Stagiaires")
    hours = models.DecimalField("Heures de formation", max_digits=12, decimal_places=2)
    sessions = models.PositiveIntegerField("Sessions")

    class Meta:
        verbose_name = "activité mensuelle de formation"
        verbose_name_plural = "activités mensuelles de formation"
        constraints = [
            models.UniqueConstraint(fields=("training", "cost_center", "month"), name="unique_monthly_training_activity"),
            models.CheckConstraint(condition=models.Q(month__day=1, hours__gte=0), name="valid_monthly_training_activity"),
        ]

    def __str__(self):
        return f"{self.training} · {self.cost_center} · {self.month:%m/%Y}"


class BudgetHistoryEvent(models.Model):
    version_id = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    envelope = models.ForeignKey(PurchaseAnnualEnvelope, on_delete=models.PROTECT, related_name="history_events")
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    actor = models.CharField(max_length=150, blank=True)
    reason = models.CharField(max_length=200)
    state = models.JSONField()

    class Meta:
        default_permissions = ()
        ordering = ["created_at", "pk"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from django.core.exceptions import ValidationError
            raise ValidationError("Un état historique est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Un état historique est immuable.")


class TransferStep(models.Model):
    transfer = models.ForeignKey(BudgetTransfer, on_delete=models.PROTECT, related_name="steps")
    active = models.BooleanField(default=True, editable=False)
    level = models.PositiveIntegerField()
    label = models.CharField(max_length=100)
    rule = models.JSONField(default=dict)
    state = models.CharField(max_length=12, default="future", choices=[("future", "Non accessible"), ("pending", "En attente"), ("unassigned", "À affecter"), ("approved", "Approuvée"), ("stopped", "Arrêtée")])
    approved_by = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL)
    approved_at = models.DateTimeField(null=True)
    evidence = models.ForeignKey("self", null=True, on_delete=models.PROTECT)

    class Meta:
        default_permissions = ()
        ordering = ["level", "pk"]
