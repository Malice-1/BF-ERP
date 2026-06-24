from django.db import models

class CostCenter(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    label = models.CharField(
        max_length=150
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class Funding(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    label = models.CharField(
        max_length=150
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class BudgetProduct(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    label = models.CharField(
        max_length=150
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} - {self.label}"


class Budget(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    year = models.IntegerField()

    class Meta:
        ordering = ["-year", "code"]

    def __str__(self):
        return f"{self.code} ({self.year})"


class BudgetLine(models.Model):
    budget = models.ForeignKey(
        Budget,
        on_delete=models.PROTECT,
        related_name="lines"
    )

    cost_center = models.ForeignKey(
        CostCenter,
        on_delete=models.PROTECT,
        related_name="budget_lines"
    )

    funding = models.ForeignKey(
        Funding,
        on_delete=models.PROTECT,
        related_name="budget_lines"
    )

    budget_product = models.ForeignKey(
        BudgetProduct,
        on_delete=models.PROTECT,
        related_name="budget_lines"
    )

    allocated_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    committed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    consumed_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    @property
    def available_amount(self):
        return (
            self.allocated_amount
            - self.committed_amount
            - self.consumed_amount
        )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "budget",
                    "cost_center",
                    "funding",
                    "budget_product",
                ],
                name="unique_budget_line"
            )
        ]

    def __str__(self):
        return (
            f"{self.budget} - "
            f"{self.budget_product}"
        )
