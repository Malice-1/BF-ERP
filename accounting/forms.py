from uuid import uuid4

from django import forms
from django.forms import inlineformset_factory
from .models import AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal, JournalEntry, JournalEntryLine


class ProfileForm(forms.ModelForm):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)

    class Meta:
        model = AccountingProfile
        fields = ("issuer", "framework", "chart_reference", "approval_note")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial["revision"] = self.instance.revision
        self.fields["issuer"].required = True


class AccountForm(forms.ModelForm):
    class Meta:
        model = Account
        fields = ("code", "label", "postable", "is_active", "party_requirement", "source_reference")


class ChartImportForm(forms.Form):
    source_reference = forms.CharField(label="Référence du plan public applicable", max_length=500)
    file = forms.FileField(label="CSV UTF-8 du plan", widget=forms.ClearableFileInput(attrs={"accept": ".csv"}))


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
