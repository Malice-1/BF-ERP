from django.db import models
from .purchase_request import PurchaseRequest
from .detailed_product import DetailedProduct
from .budget_version import BudgetVersion

class PurchaseRequestLine(models.Model):
    enough_budget=models.BooleanField(default=False)
    purchase_request=models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE)
    detailed_product=models.ForeignKey(DetailedProduct, on_delete=models.PROTECT)
    quantity=models.DecimalField(max_digits=8, decimal_places=2)
    unit_price=models.DecimalField(max_digits=12, decimal_places=2)
    budget_version=models.ForeignKey(BudgetVersion, on_delete=models.PROTECT)
