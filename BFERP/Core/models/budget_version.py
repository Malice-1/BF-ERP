from django.db import models

class BudgetVersion(models.Model):
    name=models.CharField(max_length=25, unique=True)

    def __str__(self):
        return self.name