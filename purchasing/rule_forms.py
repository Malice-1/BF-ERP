from django import forms
from django.apps import apps
from django.forms import formset_factory
from django.contrib.auth import get_user_model
from workflow.rules import schema, OPERATORS
from .models import WorkflowVersion, ApprovalRule


class RuleSetForm(forms.ModelForm):
    class Meta:
        model = WorkflowVersion
        fields = ["label"]
        labels = {"label": "Nom de la version de règles"}


class RuleForm(forms.ModelForm):
    target = forms.ChoiceField(label="Faire valider par", choices=[
        ("", "Choisir le valideur"),
        ("cdf", "Les responsables du CDF de la ligne"),
        ("support", "Les responsables du support choisi sur la DA"),
        ("role", "Un rôle ERP"), ("user", "Un utilisateur nommé"),
    ])
    junction = forms.ChoiceField(label="Appliquer cette règle si", choices=[
        ("all", "Toutes les conditions sont satisfaites (ET)"),
        ("any", "Au moins une condition est satisfaite (OU)"),
    ])
    unconditional = forms.BooleanField(label="Toujours appliquer à toutes les lignes (sans condition)", required=False)

    class Meta:
        model = ApprovalRule
        fields = ["label", "level", "role", "named_user"]
        labels = {"label": "Nom de la règle", "level": "Ordre de validation", "named_user": "Utilisateur"}
        help_texts = {"level": "Même ordre : validations en parallèle. Ordre supérieur : après les validations précédentes de la ligne."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["named_user"].queryset = get_user_model().objects.filter(is_active=True).order_by("username")
        if self.instance.pk:
            rule = self.instance
            self.initial["target"] = "cdf" if rule.cdf_manager else "support" if rule.support_manager else "role" if rule.role_id else "user" if rule.named_user_id else ""
            self.initial["junction"] = "any" if "any" in rule.conditions else "all"
            self.initial["unconditional"] = rule.conditions == {"all": []}

    def clean(self):
        data = super().clean()
        target = data.get("target")
        for name, required_target in (("role", "role"), ("named_user", "user")):
            if target == required_target and not data.get(name):
                self.add_error(name, "Choisissez une valeur pour ce mode de validation.")
            if target != required_target:
                data[name] = None
        if data.get("level", 0) < 1:
            self.add_error("level", "L’ordre doit être supérieur ou égal à 1.")
        return data

    def save(self, commit=True):
        rule = super().save(commit=False)
        rule.function = None
        rule.cdf_manager = self.cleaned_data["target"] == "cdf"
        rule.support_manager = self.cleaned_data["target"] == "support"
        if self.cleaned_data["target"] != "user":
            rule.named_user_reference = ""
        rule.mode = "cumulative"
        rule.priority = 0
        if commit:
            rule.save()
        return rule


def condition_catalog(operation="purchase"):
    return {name: {"label": field.label, "kind": field.kind,
                   "choices": [[str(obj.pk), str(obj)] for obj in apps.get_model(field.model).objects.all()] if field.model else []}
            for name, field in schema(operation).items()}


class ConditionForm(forms.Form):
    field = forms.ChoiceField(label="Information")
    op = forms.ChoiceField(label="Comparaison", choices=list(OPERATORS.items()), initial="eq")
    value = forms.CharField(label="Valeur")

    def __init__(self, *args, operation="purchase", **kwargs):
        super().__init__(*args, **kwargs)
        fields = schema(operation)
        self.fields["field"].choices = [("", "Choisir une information")] + [(key, field.label) for key, field in fields.items()]
        name = self.data.get(self.add_prefix("field")) if self.is_bound else self.initial.get("field")
        if name in fields and fields[name].model:
            self.fields["value"] = forms.ChoiceField(label="Valeur", choices=[("", "Choisir une valeur")] + [
                (str(obj.pk), str(obj)) for obj in apps.get_model(fields[name].model).objects.all()])
            self.fields["op"].choices = [(key, OPERATORS[key]) for key in ("eq", "ne")]
        else:
            self.fields["value"] = forms.DecimalField(label="Valeur", min_value=0, max_digits=28, decimal_places=10,
                widget=forms.NumberInput(attrs={"step": "any", "min": "0"}))


ConditionFormSet = formset_factory(ConditionForm, extra=1, can_delete=True, max_num=50, validate_max=True, absolute_max=60)
