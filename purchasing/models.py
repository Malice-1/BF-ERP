from django.db import models
from decimal import Decimal
from uuid import uuid4
from django.core.validators import MinValueValidator, MaxValueValidator

from django.contrib.auth import get_user_model
from suppliers.models import Supplier
from budgeting.models import DetailedProduct as BudgetDetailedProduct, CostCenter, Funding



User = get_user_model()


def request_number():
    return "DA-" + uuid4().hex[:26].upper()


class PurchaseRequest(models.Model):
    support = models.ForeignKey("budgeting.Support", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Support demandeur")

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "En validation"
        CORRECTION = "CORRECTION", "À corriger"
        REJECTED = "REJECTED", "Rejetée définitivement"
        CANCELLED = "CANCELLED", "Annulée"
        ORDERED = "ORDERED", "Commandée"

    revision = models.PositiveIntegerField(default=0, verbose_name='Révision')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Dernière modification')

    number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        default=request_number,
        verbose_name='Numéro',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Date de création',
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name="purchase_requests_created",
        verbose_name='Créé par',
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
        verbose_name='Fournisseur',
    )

    status = models.CharField(
        max_length=30,
        default=Status.DRAFT,
        choices=Status.choices,
        verbose_name='Statut',
    )

    class Meta:
        verbose_name = 'demande d’achat'
        verbose_name_plural = 'demandes d’achat'
        ordering = ["-created_at"]
        permissions = [("view_all_purchase_requests", "Consulter toutes les demandes d’achat")]

    def __str__(self):
        return self.number


class PurchaseRequestLine(models.Model):

    # Legacy VAT is unknown, never silently zero-rated.
    vat_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
     verbose_name='Taux de TVA (%)')

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name='Demande d’achat',
    )

    detailed_product = models.ForeignKey(
        BudgetDetailedProduct,
        on_delete=models.PROTECT,
        related_name="purchase_request_lines",
        verbose_name='Produit détaillé',
    )

    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        verbose_name='CDF',
    )

    funding = models.ForeignKey(
        Funding,
        on_delete=models.PROTECT,
        verbose_name='Financement',
    )

    description = models.CharField(
        max_length=255,
        verbose_name='Description',
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name='Quantité',
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name='Prix unitaire HTVA',
    )

    class Meta:
        verbose_name = 'ligne de demande d’achat'
        verbose_name_plural = 'lignes de demande d’achat'
        ordering = ["id"]

    @property
    def total_amount(self):
        return self.total_htva

    @property
    def total_htva(self):
        return self.quantity * self.unit_price

    @property
    def total_vat(self):
        if self.vat_rate is None:
            raise ValueError("Le taux de TVA doit être renseigné explicitement.")
        return self.total_htva * self.vat_rate / Decimal("100")

    @property
    def total_tvac(self):
        return self.total_htva + self.total_vat

    def __str__(self):
        return self.description


from .flow_models import (AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion,
    ApprovalRule, Submission, LineSnapshot, BudgetEntry, ApprovalStep, PurchaseOrder,
    Delegation, PurchaseNotice)  # noqa: E402,F401


class DetailedProduct(BudgetDetailedProduct):
    """Purchasing permissions/admin over the existing detailed-product table."""

    class Meta:
        proxy = True
        default_permissions = ("add", "change", "delete", "view")
        verbose_name = "produit détaillé"
        verbose_name_plural = "produits détaillés"
