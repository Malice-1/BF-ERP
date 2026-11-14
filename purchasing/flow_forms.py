from django import forms
from django.contrib.auth import get_user_model
from .forms import RevisionForm


class DecisionForm(RevisionForm):
    decision = forms.ChoiceField(label="Décision", choices=[("approve_all", "Valider tout le circuit"), ("approve", "Approuver"), ("correct", "Retourner toute la demande pour correction"), ("reject", "Rejeter définitivement toute la demande")])
    reason = forms.CharField(label="Motif (obligatoire pour correction ou rejet)", required=False, widget=forms.Textarea(attrs={"rows": 3}))


class ReassignForm(RevisionForm):
    user = forms.ModelChoiceField(label="Nouveau valideur", queryset=get_user_model().objects.filter(is_active=True))
    reason = forms.CharField(label="Justification", widget=forms.Textarea(attrs={"rows": 3}))


class DelegationForm(forms.Form):
    delegate = forms.ModelChoiceField(label="Délégué", queryset=get_user_model().objects.filter(is_active=True))
    valid_from = forms.DateTimeField(label="Début (Europe/Brussels)", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    valid_until = forms.DateTimeField(label="Fin (Europe/Brussels)", widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
