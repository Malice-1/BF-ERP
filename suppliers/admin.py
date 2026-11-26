from accounts.admin_deletion import SystemModelAdmin
from django.contrib import admin

from .models import Supplier, SupplierContact, SupplierAddress


@admin.register(Supplier)
class SupplierAdmin(SystemModelAdmin):
    exclude = ("billing_mode",)
    list_display = (
        "code",
        "name",
        "enterprise_number",
        "vat_number",
    )

    search_fields = (
        "code",
        "name",
        "enterprise_number",
        "vat_number",
    )



@admin.register(SupplierContact)
class SupplierContactAdmin(SystemModelAdmin):
    list_display = (
        "label",
        "supplier",
        "email",
        "phone",
    )

    search_fields = (
        "label",
        "firstname",
        "lastname",
        "email",
        "supplier__name",
    )


@admin.register(SupplierAddress)
class SupplierAddressAdmin(SystemModelAdmin):
    list_display = (
        "label",
        "supplier",
        "city",
        "country",
    )

    search_fields = (
        "label",
        "street",
        "city",
        "zip_code",
        "supplier__name",
    )
