from django.db import models
from .budgetary_product import BudgetaryProduct
from .supplier import Supplier

class DetailedProduct(models.Model):
    code=models.CharField(max_length=13, unique=True)
    supplier=models.ManyToManyField(Supplier)
    budgetary_product=models.ForeignKey(BudgetaryProduct, on_delete=models.CASCADE)