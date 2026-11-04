from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.contrib import admin
from django.contrib.admin.widgets import AutocompleteSelectMultiple
from django.urls import reverse
from .models import CostCenter, Support


class CostCenterManagersField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, user):
        name = user.get_full_name().strip()
        label = f"{name} ({user.username})" if name else user.username
        return f"{label} — compte inactif" if not user.is_active else label


class CostCenterManagersWidget(AutocompleteSelectMultiple):
    def get_url(self):
        return reverse(f"{self.admin_site.name}:budgeting_{self.field.model._meta.model_name}_manager_choices")


class CostCenterAdminForm(forms.ModelForm):
    managers = CostCenterManagersField(
        queryset=get_user_model().objects.none(),
        label="Responsables", required=False,
        widget=CostCenterManagersWidget(CostCenter._meta.get_field("managers"), admin.site,
            attrs={"data-minimum-input-length": 0, "data-width": "100%"}),
        help_text="Ouvrez la liste ou recherchez par nom, prénom ou identifiant. "
                  "Sélectionnez un ou plusieurs utilisateurs actifs de l’application. "
                  "Un responsable déjà affecté devenu inactif reste visible pour pouvoir le retirer.",
    )

    class Meta:
        model = CostCenter
        fields = ("code", "label", "managers")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "managers" in self.fields:
            model_field = self._meta.model._meta.get_field("managers")
            self.fields["managers"].widget = CostCenterManagersWidget(model_field, admin.site,
                attrs={"data-minimum-input-length": 0, "data-width": "100%"})
            allowed = Q(is_active=True)
            if self.instance.pk:
                allowed |= Q(**{model_field.remote_field.related_name: self.instance})
            self.fields["managers"].queryset = get_user_model().objects.filter(
                allowed).distinct().order_by("username")


class SupportAdminForm(CostCenterAdminForm):
    class Meta(CostCenterAdminForm.Meta):
        model = Support


class ManagerAssignmentForm(forms.Form):
    cost_center = forms.ModelChoiceField(CostCenter.objects.all(), label="CDF")
    user = forms.ModelChoiceField(get_user_model().objects.filter(is_active=True), label="Responsable")
    valid_from = forms.DateTimeField(label="Début (Europe/Brussels)", help_text="AAAA-MM-JJ HH:MM:SS")
    valid_until = forms.DateTimeField(label="Fin (Europe/Brussels)", required=False)


class EndManagerAssignmentForm(forms.Form):
    valid_until = forms.DateTimeField(label="Fin de l’affectation (Europe/Brussels)")


class EntityManagersForm(forms.Form):
    kind = forms.ChoiceField(label="Type", choices=[("cdf", "CDF"), ("support", "Support")])
    entity_id = forms.IntegerField(widget=forms.HiddenInput)
    managers = forms.ModelMultipleChoiceField(
        get_user_model().objects.filter(is_active=True), label="Responsables", required=False,
        widget=forms.CheckboxSelectMultiple)
