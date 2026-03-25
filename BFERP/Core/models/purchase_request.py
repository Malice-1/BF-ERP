from django.db import models
from .custom_user import CustomUser
from .budget_version import BudgetVersion

class PurchaseRequest(models.Model):
    applicant=models.ForeignKey(CustomUser, on_delete=models.PROTECT)
    budget_version=models.ForeignKey(BudgetVersion, on_delete=models.PROTECT)
