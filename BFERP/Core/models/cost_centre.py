from django.db import models
from .custom_user import CustomUser

class CostCentre(models.Model):
    name=models.CharField(max_length=150, unique=True)
    responsible=models.ForeignKey(CustomUser, on_delete=models.PROTECT)

    def __str__(self):
        return self.name