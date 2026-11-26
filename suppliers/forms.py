from django import forms
from .models import Supplier


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "code", "name", "enterprise_number", "vat_number", "bank_account",
            "street", "zip_code", "city", "country", "phone", "mobile", "contact_person", "email",
        ]
