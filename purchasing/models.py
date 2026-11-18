from django.db import models, transaction
from decimal import Decimal
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator

from django.contrib.auth import get_user_model
from suppliers.models import Supplier
from budgeting.models import DetailedProduct as BudgetDetailedProduct, CostCenter, Funding



User = get_user_model()


class PurchaseRequestSequence(models.Model):
    """Persistent annual counter, locked during number allocation."""

    year = models.PositiveIntegerField(primary_key=True)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()


def request_number():
    with transaction.atomic():
        counter, _ = PurchaseRequestSequence.objects.select_for_update().get_or_create(
            year=timezone.localdate().year
        )
        counter.last_number += 1
        counter.save(update_fields=["last_number"])
        return f"DA-{counter.year}-{counter.last_number:04d}"


class FrameworkContract(models.Model):
    reference = models.CharField("Référence du contrat", max_length=80, unique=True)
    title = models.CharField("Intitulé", max_length=255)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, verbose_name="Fournisseur")
    start_date = models.DateField("Début de validité")
    end_date = models.DateField("Fin de validité")
    ceiling = models.DecimalField("Plafond TVAC en EUR", max_digits=28, decimal_places=10, blank=True, null=True,
                                  validators=[MinValueValidator(Decimal("0.01"))])
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["reference"]
        verbose_name = "contrat-cadre"
        verbose_name_plural = "contrats-cadres"
        default_permissions = ("view", "add", "change")
        constraints = [
            models.CheckConstraint(condition=models.Q(start_date__lte=models.F("end_date")), name="framework_valid_dates"),
            models.CheckConstraint(condition=models.Q(ceiling__isnull=True) | models.Q(ceiling__gt=0), name="framework_positive_ceiling"),
        ]

    def __str__(self):
        return f"{self.reference} · {self.title}"


class FrameworkContractPrice(models.Model):
    contract = models.ForeignKey(FrameworkContract, on_delete=models.PROTECT, related_name="prices")
    product = models.ForeignKey(BudgetDetailedProduct, on_delete=models.PROTECT, verbose_name="Produit détaillé")
    unit_price = models.DecimalField("Prix unitaire HTVA", max_digits=12, decimal_places=2,
                                    validators=[MinValueValidator(Decimal("0"))])
    vat_rate = models.DecimalField("TVA (%)", max_digits=7, decimal_places=4,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))])
    is_active = models.BooleanField("Disponible", default=True)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["contract", "product"], name="framework_unique_product_price")]


class PurchaseRequest(models.Model):
    framework_contract = models.ForeignKey(FrameworkContract, on_delete=models.PROTECT, blank=True, null=True,
        related_name="purchase_requests", verbose_name="Contrat-cadre")
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
        permissions = [("decide_any_purchaserequest", "Intervenir sur toutes les validations des demandes d’achat"), ("view_all_purchase_requests", "Consulter toutes les demandes d’achat")]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.number:
            with transaction.atomic():
                self.number = request_number()
                return super().save(*args, **kwargs)
        return super().save(*args, **kwargs)

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
