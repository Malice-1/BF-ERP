from django.contrib import admin

from .models import PurchaseRequest, PurchaseRequestLine
from accounts.admin import ReadOnlyAdmin
from . import flow_admin  # noqa: F401
from .flow_admin import FinancialReadOnlyAdmin

class PurchaseRequestLineInline(admin.TabularInline):
    model = PurchaseRequestLine
    extra = 1

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(FinancialReadOnlyAdmin):

    list_display = (
        "number",
        "supplier",
        "created_by",
        "status",
        "created_at",
    )

    search_fields = (
        "number",
        "supplier__name",
        "created_by__username",
    )

    list_filter = (
        "status",
        "supplier",
        "created_at",
    )

    readonly_fields = (
        "number",
        "created_at",
    )

    inlines = [
        PurchaseRequestLineInline,
    ]

@admin.register(PurchaseRequestLine)
class PurchaseRequestLineAdmin(FinancialReadOnlyAdmin):

    @admin.display(description="Total HTVA")
    def total_amount(self, obj):
        return obj.total_amount

    list_display = (
        "purchase_request",
        "detailed_product",
        "cost_center",
        "funding",
        "quantity",
        "unit_price",
        "total_amount",
    )

    list_filter = (
        "cost_center",
        "funding",
    )

    search_fields = (
        "purchase_request__number",
        "description",
        "detailed_product__label"
    )
