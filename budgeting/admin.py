from django.contrib import admin

from .models import CostCenter, Funding, BudgetProduct, Budget, BudgetLine, DetailedProduct


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
        "is_active",
    )

    search_fields = (
        "code",
        "year",
        "is_active",
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


@admin.register(DetailedProduct)
class DetailedProductAdmin(admin.ModelAdmin):

    list_display = (
        "code",
        "label",
        "budget_product",
    )

    search_fields = (
        "code",
        "label",
        "budget_product__code",
    )

    list_filter = (
        "budget_product",
    )
