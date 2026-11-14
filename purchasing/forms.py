from django import forms
from decimal import Decimal
from django.template.defaultfilters import floatformat
from .models import PurchaseRequest, PurchaseRequestLine
from budgeting.models import BudgetProduct, CostCenter, Funding
from .models import EnvelopeVersion


class BudgetAmountInput(forms.NumberInput):
    def format_value(self, value):
        if isinstance(value, Decimal):
            return floatformat(value, "2u")
        return super().format_value(value)


class BudgetVersionChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        state = "Bloquée" if obj.locked_at else "Active" if obj.envelope.active_version_id == obj.pk else (
            "Publiée · remplacée" if obj.published_at else "Brouillon")
        if obj.published_at and obj.editing_unlocked_at:
            state += " · modifications débloquées"
        return f"{obj.envelope.year} · {obj.label} · {state} (#{obj.pk})"


class BudgetVersionSelectionForm(forms.Form):
    version = BudgetVersionChoiceField(label="Version budgétaire", queryset=EnvelopeVersion.objects.filter(deleted_at__isnull=True).select_related(
        "envelope").order_by("-envelope__year", "-pk"))


class BudgetCheckForm(BudgetVersionSelectionForm):
    budget_product = forms.ModelChoiceField(label="Produit budgétaire", queryset=BudgetProduct.objects.all())
    funding = forms.ModelChoiceField(label="Financement", queryset=Funding.objects.all())
    cost_center = forms.ModelChoiceField(label="CDF", queryset=CostCenter.objects.all())


class PurchaseRequestForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["support"].queryset = user.supports.all() if user else self.fields["support"].queryset.none()
        self.fields["support"].help_text = "Choisissez votre support d’appartenance, si nécessaire. Chaque ligne est validée par le responsable de son CDF."

    class Meta:
        model = PurchaseRequest
        fields = ["supplier", "support"]
        labels = {"supplier": "Fournisseur"}


class RevisionForm(forms.Form):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class EditPurchaseRequestForm(PurchaseRequestForm):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class DetailedProductChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f"{obj.code} - {obj.label} · BI : {obj.budget_product}"


class PurchaseRequestLineForm(forms.ModelForm):
    expected_revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)

    @property
    def budget_product_labels(self):
        return {str(product.pk): str(product.budget_product)
                for product in self.fields["detailed_product"].queryset}

    class Meta:
        model = PurchaseRequestLine
        fields = ["detailed_product", "description", "quantity", "unit_price", "vat_rate", "cost_center", "funding"]
        labels = {"detailed_product": "Produit", "description": "Description", "quantity": "Quantité",
                  "unit_price": "Prix unitaire HTVA", "vat_rate": "Taux de TVA (%)",
                  "cost_center": "CDF", "funding": "Financement"}
        field_classes = {"detailed_product": DetailedProductChoiceField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["detailed_product"].queryset = self.fields["detailed_product"].queryset.select_related("budget_product")
        self.fields["vat_rate"].required = True
