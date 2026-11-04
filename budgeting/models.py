from django.db import models

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
