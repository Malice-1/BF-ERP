from uuid import uuid4

from django import forms
from django.forms import inlineformset_factory

from .models import Customer, IssuerConfiguration, TrainingService, SalesOrder, SalesOrderLine, InvoicePayment


BILLING_FIELDS = ("invoice_format", "payment_days", "payment_terms", "peppol_endpoint_id", "peppol_endpoint_scheme")


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("code", "name", "street", "zip_code", "city", "country", "vat_number", "email", "reference",
            "is_active", *BILLING_FIELDS)

    def __init__(self, *args, can_bill=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference"].label = "Référence acheteur / client (routage XML)"
        if not can_bill:
            for name in BILLING_FIELDS:
                self.fields.pop(name)


class CustomerBillingForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = BILLING_FIELDS


class IssuerForm(forms.ModelForm):
    class Meta:
        model = IssuerConfiguration
        exclude = ("id",)


class TrainingForm(forms.ModelForm):
    class Meta:
        model = TrainingService
        fields = ("code", "description", "unit", "is_active")


class OrderForm(forms.ModelForm):
    revision = forms.IntegerField(widget=forms.HiddenInput, min_value=0, initial=0)

    class Meta:
        model = SalesOrder
        fields = ("customer", "order_date", "customer_reference", "currency", "notes")
        widgets = {"order_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = Customer.objects.filter(is_active=True)
        if self.instance.pk:
            self.initial["revision"] = self.instance.revision


LINE_FIELDS = ("service", "description", "quantity", "unit", "unit_price", "discount", "tax_code", "tax_rate",
    "exemption_reason", "service_start", "service_end", "cost_center", "funding", "budget_product", "support")


class LineForm(forms.ModelForm):
    class Meta:
        model = SalesOrderLine
        fields = LINE_FIELDS
        widgets = {field: forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
            for field in ("service_start", "service_end")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = TrainingService.objects.filter(is_active=True)


LineFormSet = inlineformset_factory(SalesOrder, SalesOrderLine, form=LineForm,
    fields=LINE_FIELDS, extra=1, can_delete=True, min_num=1, validate_min=True,
    max_num=100, validate_max=True, absolute_max=110)


class PaymentForm(forms.ModelForm):
    token = forms.UUIDField(widget=forms.HiddenInput, initial=uuid4)

    class Meta:
        model = InvoicePayment
        fields = ("amount", "payment_date", "reference")
        widgets = {"payment_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}


class RevisionForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)


class ReversalForm(forms.Form):
    reason = forms.CharField(label="Motif de correction", max_length=255)
