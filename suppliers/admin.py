from django.contrib import admin

from .models import Supplier, SupplierContact, SupplierAddress


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "vat_number",
    )

    search_fields = (
        "code",
        "name",
        "vat_number",
    )



@admin.register(SupplierContact)
class SupplierContactAdmin(admin.ModelAdmin):
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
class SupplierAddressAdmin(admin.ModelAdmin):
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
