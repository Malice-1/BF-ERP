from django.contrib import admin
from config.admin_search import SearchColumnsAdminMixin
from .models import Customer, TrainingService, IssuerConfiguration, SalesOrder, SalesInvoice


class SalesReadOnlyAdmin(SearchColumnsAdminMixin, admin.ModelAdmin):
    """Mutations use the audited application services, including for superusers."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Customer)
class CustomerAdmin(SalesReadOnlyAdmin):
    list_display = ("code", "name", "invoice_format", "is_active")
    search_fields = ("code", "name")


@admin.register(TrainingService)
class TrainingAdmin(SalesReadOnlyAdmin):
    list_display = ("code", "description", "is_active")


@admin.register(SalesOrder)
class OrderAdmin(SalesReadOnlyAdmin):
    list_display = ("number", "customer", "status", "total")
    list_filter = ("status",)


@admin.register(SalesInvoice)
class InvoiceAdmin(SalesReadOnlyAdmin):
    list_display = ("number", "issue_date", "document_status", "payment_status", "total")
    list_filter = ("document_status", "payment_status", "invoice_format")


admin.site.register(IssuerConfiguration, SalesReadOnlyAdmin)
