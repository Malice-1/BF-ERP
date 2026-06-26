from django.contrib import admin

from .models import PurchaseRequest


@admin.register(PurchaseRequest)
class PurchaseRequestAdmin(admin.ModelAdmin):

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
        "created_at",
    )
