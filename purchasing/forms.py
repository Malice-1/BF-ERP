from django import forms
from decimal import Decimal
from django.template.defaultfilters import floatformat
from .framework_contracts import available_contracts
from .models import FrameworkContract, FrameworkContractPrice, PurchaseRequest, PurchaseRequestLine
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
        self.fields["supplier"].required = False
        self.fields["supplier"].help_text = "Obligatoire pour une demande sans contrat-cadre."
        contract_field = self.fields["framework_contract"]
        contracts = available_contracts()
        if self.instance.framework_contract_id:
            contracts = contracts | FrameworkContract.objects.filter(pk=self.instance.framework_contract_id)
        contract_field.queryset = contracts.select_related("supplier")
        contract_field.label_from_instance = lambda contract: f"{contract} · {contract.supplier}"
        contract_field.empty_label = "Sans contrat-cadre"
        contract_field.help_text = "Le contrat sélectionné fournit le fournisseur et les tarifs du catalogue."
        if self.instance.pk and self.instance.lines.exists():
            contract_field.disabled = True
            contract_field.help_text = "Retirez les lignes pour changer le contrat-cadre."

    def clean(self):
        values = super().clean()
        contract, supplier = values.get("framework_contract"), values.get("supplier")
        if not contract and not supplier:
            self.add_error("supplier", "Sélectionnez un fournisseur pour une demande sans contrat-cadre.")
        elif contract and supplier and supplier.pk != contract.supplier_id:
            self.add_error("supplier", "Le fournisseur doit correspondre au contrat-cadre.")
        elif contract:
            values["supplier"] = contract.supplier
        return values

    class Meta:
        model = PurchaseRequest
        fields = ["framework_contract", "supplier", "support"]
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
        if "vat_rate" in self.fields:
            self.fields["vat_rate"].required = True


class FrameworkPurchaseLineForm(PurchaseRequestLineForm):
    class Meta(PurchaseRequestLineForm.Meta):
        fields = ["detailed_product", "description", "quantity", "cost_center", "funding"]

    def __init__(self, *args, contract, **kwargs):
        super().__init__(*args, **kwargs)
        prices = {row.product_id: row for row in contract.prices.filter(is_active=True)}
        product = self.fields["detailed_product"]
        product.queryset = product.queryset.filter(pk__in=prices)
        label = product.label_from_instance
        product.label_from_instance = lambda item: f"{label(item)} · {prices[item.pk].unit_price:.2f} EUR HTVA"
        product.help_text = "Le prix et le taux de TVA du catalogue sont appliqués à l’enregistrement."


class FrameworkContractForm(forms.ModelForm):
    class Meta:
        model = FrameworkContract
        fields = ("reference", "title", "supplier", "start_date", "end_date", "ceiling", "is_active")
        widgets = {field: forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
                   for field in ("start_date", "end_date")}


class FrameworkPriceForm(forms.ModelForm):
    class Meta:
        model = FrameworkContractPrice
        fields = ("product", "unit_price", "vat_rate", "is_active")
