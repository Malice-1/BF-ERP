from django.db import models
from decimal import Decimal
from uuid import uuid4
from django.core.validators import MinValueValidator, MaxValueValidator

from django.contrib.auth import get_user_model
from suppliers.models import Supplier
from budgeting.models import DetailedProduct, CostCenter, Funding



User = get_user_model()


def request_number():
    return "DA-" + uuid4().hex[:26].upper()


class PurchaseRequest(models.Model):

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        SUBMITTED = "SUBMITTED", "En validation"
        CORRECTION = "CORRECTION", "À corriger"
        REJECTED = "REJECTED", "Rejetée définitivement"
        CANCELLED = "CANCELLED", "Annulée"
        ORDERED = "ORDERED", "Commandée"

    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    number = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        default=request_number
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="purchase_requests_created"
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_requests"
    )

    status = models.CharField(
        max_length=30,
        default=Status.DRAFT,
        choices=Status.choices
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PurchaseRequestLine(models.Model):

    # Legacy VAT is unknown, never silently zero-rated.
    vat_rate = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    purchase_request = models.ForeignKey(
        PurchaseRequest,
        on_delete=models.CASCADE,
        related_name="lines"
    )

    detailed_product = models.ForeignKey(
        DetailedProduct,
        on_delete=models.PROTECT,
        related_name="purchase_request_lines"
    )

    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT
    )

    funding = models.ForeignKey(
        Funding,
        on_delete=models.PROTECT
    )

    description = models.CharField(
        max_length=255
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=1,
        validators=[MinValueValidator(Decimal("0.01"))]
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))]
    )

    class Meta:
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
