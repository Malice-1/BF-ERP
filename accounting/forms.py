from uuid import uuid4

from django import forms
from django.forms import inlineformset_factory
from budgeting.models import BudgetProduct
from .models import (AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal, JournalEntry,
    JournalEntryLine, PurchasePostingConfiguration, SalesPostingConfiguration)


class PurchasePostingForm(forms.ModelForm):
    journal = forms.ModelChoiceField(label="Journal des engagements", queryset=Journal.objects.filter(is_active=True))
    offset_account = forms.ModelChoiceField(label="Compte de contrepartie",
        queryset=Account.objects.filter(is_active=True, postable=True).exclude(party_requirement="CUSTOMER"))

    class Meta:
        model = PurchasePostingConfiguration
        fields = ("journal", "offset_account", "enabled")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for field in ("journal", "offset_account"):
                choices = self.fields[field].queryset
                self.fields[field].queryset = choices | choices.model.objects.filter(
                    pk=getattr(self.instance, field + "_id"))

    def clean(self):
        values = super().clean()
        if values.get("enabled"):
            journal, account = values.get("journal"), values.get("offset_account")
            if journal and not journal.is_active:
                self.add_error("journal", "Le journal doit être actif.")
            if account and (not account.is_active or not account.postable or account.party_requirement == "CUSTOMER"):
                self.add_error("offset_account", "Choisissez un compte d’imputation actif compatible avec les achats.")
        return values


class BudgetProductAccountForm(forms.Form):
    product = forms.ModelChoiceField(label="Produit budgétaire", queryset=BudgetProduct.objects.all())
    account = forms.ModelChoiceField(label="Compte d’imputation",
        queryset=Account.objects.filter(is_active=True, postable=True).exclude(party_requirement="CUSTOMER"))


class SalesPostingForm(forms.ModelForm):
    class Meta:
        model = SalesPostingConfiguration
        fields = ("journal", "receivable_account", "tax_account", "enabled")
        help_texts = {"tax_account": "Obligatoire pour les factures avec TVA."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        accounts = Account.objects.filter(is_active=True, postable=True)
        for field, choices in {
            "journal": Journal.objects.filter(is_active=True, kind="SALE"),
            "receivable_account": accounts.exclude(party_requirement="SUPPLIER"),
            "tax_account": accounts.filter(party_requirement="NONE"),
        }.items():
            current = getattr(self.instance, field + "_id")
            self.fields[field].queryset = choices | choices.model.objects.filter(pk=current) if current else choices

    def clean(self):
        values = super().clean()
        if values.get("enabled"):
            journal, receivable, tax = (values.get(field) for field in ("journal", "receivable_account", "tax_account"))
            if journal and (not journal.is_active or journal.kind != "SALE"):
                self.add_error("journal", "Choisissez un journal de ventes actif.")
            if receivable and (not receivable.is_active or not receivable.postable or receivable.party_requirement == "SUPPLIER"):
                self.add_error("receivable_account", "Choisissez un compte d’imputation actif compatible avec un client.")
            if tax and (not tax.is_active or not tax.postable or tax.party_requirement != "NONE"):
                self.add_error("tax_account", "Choisissez un compte d’imputation actif sans tiers obligatoire.")
            if tax and tax == receivable:
                self.add_error("tax_account", "Choisissez un compte distinct du compte clients.")
        return values


class SalesBudgetProductAccountForm(BudgetProductAccountForm):
    account = forms.ModelChoiceField(label="Compte de produit",
        queryset=Account.objects.filter(is_active=True, postable=True, party_requirement="NONE"))


class ProfileForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)

    class Meta:
        model = AccountingProfile
        fields = ("issuer", "framework", "chart_reference")
        labels = {"chart_reference": "Référence du plan actuel (facultative)"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["revision"] = self.instance.revision
        self.fields["issuer"].required = True


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ("code", "label", "postable", "is_active", "party_requirement", "source_reference")


class JournalForm(forms.ModelForm):
    class Meta:
        model = Journal
        fields = ("code", "label", "kind", "is_active")


class YearForm(forms.ModelForm):
    class Meta:
        model = FiscalYear
        fields = ("code", "start_date", "end_date")
        widgets = {key: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for key in ("start_date", "end_date")}


class PeriodForm(forms.ModelForm):
    class Meta:
        model = AccountingPeriod
        fields = ("fiscal_year", "label", "start_date", "end_date")
        widgets = {key: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for key in ("start_date", "end_date")}


class EntryForm(forms.ModelForm):
    token = forms.UUIDField(initial=uuid4, widget=forms.HiddenInput)
    revision = forms.IntegerField(min_value=0, initial=0, widget=forms.HiddenInput)

    class Meta:
        model = JournalEntry
        fields = ("journal", "period", "accounting_date", "document_date", "description", "document_reference")
        widgets = {key: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d") for key in ("accounting_date", "document_date")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["journal"].queryset = Journal.objects.filter(is_active=True)
        self.fields["period"].queryset = AccountingPeriod.objects.filter(is_open=True, fiscal_year__is_open=True).select_related("fiscal_year")
        if self.instance.pk:
            self.initial.update(token=self.instance.idempotency_key, revision=self.instance.revision)


class LineForm(forms.ModelForm):
    class Meta:
        model = JournalEntryLine
        fields = ("account", "description", "debit", "credit", "customer", "supplier")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["account"].queryset = Account.objects.filter(is_active=True, postable=True)


EntryLineFormSet = inlineformset_factory(JournalEntry, JournalEntryLine, form=LineForm,
    extra=1, min_num=2, validate_min=True, max_num=200, validate_max=True, absolute_max=210, can_delete=True)


class RevisionForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class PeriodStateForm(forms.Form):
    reason = forms.CharField(label="Justification", max_length=255)


class ReversalForm(forms.Form):
    period = forms.ModelChoiceField(label="Période de contrepassation", queryset=AccountingPeriod.objects.none())
    accounting_date = forms.DateField(label="Date comptable de contrepassation", widget=forms.DateInput(attrs={"type": "date"}))
    reason = forms.CharField(label="Motif", max_length=255)
    token = forms.UUIDField(initial=uuid4, widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["period"].queryset = AccountingPeriod.objects.filter(is_open=True, fiscal_year__is_open=True).select_related("fiscal_year")
