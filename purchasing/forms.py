from django import forms
from .models import PurchaseRequest, PurchaseRequestLine


class PurchaseRequestForm(forms.ModelForm):
    class Meta:
        model = PurchaseRequest
        fields = ["supplier"]
        labels = {"supplier": "Fournisseur"}


class RevisionForm(forms.Form):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class EditPurchaseRequestForm(PurchaseRequestForm):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class PurchaseRequestLineForm(forms.ModelForm):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    class Meta:
        model = PurchaseRequestLine
        fields = ["detailed_product", "description", "quantity", "unit_price", "vat_rate", "cost_center", "funding"]
        labels = {"detailed_product": "Produit", "description": "Description", "quantity": "Quantité",
                  "unit_price": "Prix unitaire HTVA", "vat_rate": "Taux de TVA (%)",
                  "cost_center": "CDF", "funding": "Financement"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vat_rate"].required = True
