from django.contrib import admin

from .models import CostCenter, Funding, BudgetProduct, Budget, BudgetLine


@admin.register(CostCenter)
class CostCenterAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
    )

    search_fields = (
        "code",
        "label",
    )

@admin.register(Funding)
class FundingAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
    )

    search_fields = (
        "code",
        "label",
    )


@admin.register(BudgetProduct)
class BudgetProductAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "label",
    )

    search_fields = (
        "code",
        "label",
    )


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "year",
    )

    search_fields = (
        "code",
        "year",
    )



@admin.register(BudgetLine)
class BudgetLineAdmin(admin.ModelAdmin):
    list_display = (
        "budget",
        "cost_center",
        "funding",
        "budget_product",
        "allocated_amount",
        "committed_amount",
        "consumed_amount",
    )

    search_fields = (
        "budget__code",
        "cost_center__code",
        "funding__code",
        "budget_product__code",
    )
