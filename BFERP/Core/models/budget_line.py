from django.db import models
from .cost_centre import CostCentre
from .funding import Funding
from .budgetary_product import BudgetaryProduct
from .budget_version import BudgetVersion

class BudgetLine(models.Model):
    cost_centre=models.ForeignKey(CostCentre, on_delete=models.PROTECT)
    funding=models.ForeignKey(Funding, on_delete=models.PROTECT)
    budgetary_product=models.ForeignKey(BudgetaryProduct, on_delete=models.PROTECT)
    budget_version=models.ForeignKey(BudgetVersion, on_delete=models.PROTECT)
    amount_total=models.DecimalField(max_digits=12, decimal_places=2)
    amount_committed=models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.budgetary_product} - {self.cost_centre} - {self.funding} - {self.budget_version}"

    class Meta:
        indexes= [
            models.Index(fields=['budget_version']),
            models.Index(fields=['cost_centre', 'funding', 'budgetary_product'])
        ]