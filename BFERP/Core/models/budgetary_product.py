from django.db import models

class BudgetaryProduct(models.Model):
    code=models.CharField(max_length=14, unique=True)
    description=models.TextField()

    def __str__(self):
        return self.code