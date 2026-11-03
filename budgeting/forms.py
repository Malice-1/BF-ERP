from django import forms
from django.contrib.auth import get_user_model
from .models import CostCenter


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
