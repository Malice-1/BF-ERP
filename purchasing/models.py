from django.db import models

from django.contrib.auth import get_user_model
from suppliers.models import Supplier
from budgeting.models import DetailedProduct, CostCenter, Funding



User = get_user_model()


class PurchaseRequest(models.Model):

    number = models.CharField(
        max_length=30,
        unique=True,
        editable=False
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
        default="DRAFT"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class PurchaseRequestLine(models.Model):

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
        default=1
    )

    unit_price = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    class Meta:
        ordering = ["id"]

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.description
