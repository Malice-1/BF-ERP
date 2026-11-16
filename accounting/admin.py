from django.contrib import admin
from .models import AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal, JournalEntry
from .models import SupplierInvoice


class LedgerReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in (AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal, JournalEntry, SupplierInvoice):
    admin.site.register(model, LedgerReadOnlyAdmin)
