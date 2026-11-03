from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from budgeting.models import CostCenter, Funding, BudgetProduct
from .models import ValidationFunction


class LoginForm(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Identifiants de connexion incorrects.",
        "inactive": "Ce compte est désactivé. Contactez votre administrateur.",
    }

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError as error:
            # Le backend refuse les comptes inactifs avant que le formulaire
            # puisse distinguer ce cas d'un mauvais mot de passe.
            username = self.cleaned_data.get("username")
            password = self.cleaned_data.get("password")
            if error.code == "invalid_login" and username and password:
                User = get_user_model()
                try:
                    user = User._default_manager.get_by_natural_key(username)
                except User.DoesNotExist:
                    pass
                else:
                    if not user.is_active and user.check_password(password):
                        raise forms.ValidationError(self.error_messages["inactive"], code="inactive") from error
            raise


class AuthorizationForm(forms.Form):
    user = forms.ModelChoiceField(get_user_model().objects.all(), label="Utilisateur")
    function = forms.ModelChoiceField(ValidationFunction.objects.all(), label="Fonction")
    valid_from = forms.DateTimeField(label="Début de validité (Europe/Brussels)", help_text="AAAA-MM-JJ HH:MM:SS")
    valid_until = forms.DateTimeField(label="Fin de validité (Europe/Brussels)", required=False)
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
