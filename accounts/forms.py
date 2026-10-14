from django import forms
from django.contrib.auth import get_user_model
from budgeting.models import CostCenter, Funding, BudgetProduct
from .models import ValidationFunction


class AuthorizationForm(forms.Form):
    user = forms.ModelChoiceField(get_user_model().objects.all(), label="Utilisateur")
    function = forms.ModelChoiceField(ValidationFunction.objects.all(), label="Fonction")
    valid_from = forms.DateTimeField(label="Début de validité (UTC)", help_text="AAAA-MM-JJ HH:MM:SS")
    valid_until = forms.DateTimeField(label="Fin de validité (UTC)", required=False)
    enabled = forms.BooleanField(label="Habilitation activée", required=False, initial=True)
    cost_centers = forms.ModelMultipleChoiceField(CostCenter.objects.all(), required=False, label="CDF")
    fundings = forms.ModelMultipleChoiceField(Funding.objects.all(), required=False, label="Financements")
    budget_products = forms.ModelMultipleChoiceField(BudgetProduct.objects.all(), required=False, label="Produits budgétaires")
    expected_version = forms.IntegerField(required=False, widget=forms.HiddenInput)

    def command_data(self):
        values = self.cleaned_data.copy()
        scope = {}
        for field, key in (("cost_centers", "cost_center"), ("fundings", "funding"), ("budget_products", "budget_product")):
            selected = values.pop(field)
            if selected:
                scope[key] = list(selected.values_list("pk", flat=True))
        values["scope"] = scope
        return values
