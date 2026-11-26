from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django import forms
from django.forms import model_to_dict
from config.list_search import filter_rows
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from suppliers.models import Supplier
from .models import SupplierInvoice, AccountingEvent
from . import supplier_manual, supplier_xml
from .services import audit, require


class UploadForm(forms.Form):
    file = forms.FileField(label="Facture fournisseur XML Peppol", widget=forms.ClearableFileInput(attrs={"accept": ".xml,application/xml,text/xml"}))


class ReviewForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    supplier = forms.ModelChoiceField(label="Fournisseur existant", queryset=Supplier.objects.all(), required=False)
    note = forms.CharField(label="Justification de revue / rejet", max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))
    action = forms.ChoiceField(label="Décision", choices=[("approve", "Approuver"), ("reject", "Rejeter")])

    def __init__(self, *args, invoice, **kwargs):
        super().__init__(*args, **kwargs)
        if invoice.origin == "MANUAL":
            del self.fields["supplier"]


class ManualInvoiceForm(forms.Form):
    revision = forms.IntegerField(min_value=0, required=False, widget=forms.HiddenInput)
    supplier = forms.ModelChoiceField(label="Fournisseur", queryset=Supplier.objects.all())
    invoice_number = forms.CharField(label="Numéro de facture", max_length=255)
    issue_date = forms.DateField(label="Date de facture", widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    due_date = forms.DateField(label="Échéance", required=False, widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))
    currency = forms.RegexField(label="Devise", regex=r"^[A-Za-z]{3}$", initial="EUR", max_length=3)
    subtotal = forms.DecimalField(label="Montant HT", min_value=0, max_digits=20, decimal_places=2)
    tax_total = forms.DecimalField(label="Montant TVA", min_value=0, max_digits=20, decimal_places=2)
    payable = forms.DecimalField(label="Montant à payer", min_value=0, max_digits=20, decimal_places=2,
        required=False, help_text="Le total TTC est utilisé par défaut.")
    order_reference = forms.CharField(label="Référence de commande", max_length=255, required=False)
    description = forms.CharField(label="Description", max_length=2000, required=False,
        widget=forms.Textarea(attrs={"rows": 3}))

    def clean_currency(self):
        return self.cleaned_data["currency"].upper()


@login_required
@require_http_methods(["GET", "POST"])
def manual_edit(request, pk=None):
    permission = "change_supplierinvoice" if pk else "add_supplierinvoice"
    require(request.user, permission)
    invoice = get_object_or_404(SupplierInvoice, pk=pk, origin="MANUAL", status="RECEIVED") if pk else None
    initial = {**model_to_dict(invoice, fields=list(ManualInvoiceForm.base_fields)), **invoice.extracted_data} if invoice else None
    form = ManualInvoiceForm(request.POST if request.method == "POST" else None, initial=initial)
    form.fields["revision"].required = bool(invoice)
    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data.copy()
        revision = values.pop("revision")
        try:
            saved = supplier_manual.save_invoice(actor=request.user, values=values, pk=pk, revision=revision)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        else:
            messages.success(request, "Facture fournisseur enregistrée.")
            if request.user.has_perm("accounting.view_supplierinvoice"):
                return redirect("accounting:supplier_invoice_detail", pk=saved.pk)
            return redirect("accounting:home")
    back_url = None
    if request.user.has_perm("accounting.view_supplierinvoice"):
        back_url = (reverse("accounting:supplier_invoice_detail", args=[pk]) if pk
                    else reverse("accounting:supplier_invoices"))
    return render(request, "accounting/form.html", {"form": form,
        "title": "Modifier la facture fournisseur" if pk else "Encoder une facture fournisseur",
        "intro": "Saisissez les montants HT et TVA de la facture. Le total TTC est calculé à l’enregistrement.",
        "back_url": back_url})

@login_required
@permission_required("accounting.view_supplierinvoice", raise_exception=True)
@require_GET
def invoice_list(request):
    rows = SupplierInvoice.objects.select_related("supplier").prefetch_related("validations")
    rows, _ = filter_rows(request, rows, {
        "number": ("Numéro", "invoice_number__icontains"),
        "supplier": ("Fournisseur", "extracted_data__seller__name__icontains", "supplier__name__icontains"),
    })
    if request.GET.get("status") in ("RECEIVED", "REVIEWED", "REJECTED"):
        rows = rows.filter(status=request.GET["status"])
    if request.GET.get("origin") in ("MANUAL", "PEPPOL"):
        rows = rows.filter(origin=request.GET["origin"])
    return render(request, "accounting/supplier_invoices.html", {"page": Paginator(rows, 50).get_page(request.GET.get("page"))})


@login_required
@permission_required("accounting.import_supplierinvoice", raise_exception=True)
@require_http_methods(["GET", "POST"])
def upload(request):
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            from django.conf import settings
            file = form.cleaned_data["file"]
            if file.size > settings.SUPPLIER_XML_MAX_BYTES:
                raise ValidationError("Le fichier dépasse la taille autorisée.")
            invoice, created = supplier_xml.import_invoice(actor=request.user,
                data=file.read(settings.SUPPLIER_XML_MAX_BYTES + 1), filename=file.name)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        except OSError:
            form.add_error(None, "L’archivage a échoué. Aucune facture n’a été enregistrée ; contactez l’administrateur.")
        else:
            messages.success(request, "XML importé. Vérifiez son résultat de validation et les données extraites." if created else "Ce fichier était déjà importé ; aucune facture supplémentaire créée.")
            return redirect("accounting:supplier_invoice_detail", pk=invoice.pk) if request.user.has_perm("accounting.view_supplierinvoice") else redirect("accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Importer une facture Peppol",
        "intro": "Chargez une facture XML Peppol BIS Billing 3.0 de type 380. Le fichier original est archivé et les données importées passent en revue.",
        "back_url": reverse("accounting:supplier_invoices") if request.user.has_perm("accounting.view_supplierinvoice") else None})


@login_required
@permission_required("accounting.view_supplierinvoice", raise_exception=True)
@require_GET
def detail(request, pk):
    invoice = get_object_or_404(SupplierInvoice.objects.select_related("supplier"), pk=pk)
    candidates = supplier_xml.supplier_candidates(invoice) if invoice.origin == "PEPPOL" else []
    initial = {"revision": invoice.revision}
    if len(candidates) == 1:
        initial["supplier"] = candidates[0].pk
    return render(request, "accounting/supplier_invoice_detail.html", {"invoice": invoice,
        "latest": invoice.validations.first(), "runs": invoice.validations.all(),
        "events": AccountingEvent.objects.filter(object_type=invoice._meta.label_lower, object_identifier=str(invoice.pk)),
        "review_form": ReviewForm(invoice=invoice, initial=initial), "candidates": candidates})


@login_required
@permission_required("accounting.review_supplierinvoice", raise_exception=True)
@require_POST
def review(request, pk):
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
    form = ReviewForm(request.POST, invoice=invoice)
    if form.is_valid():
        try:
            supplier_xml.review_invoice(actor=request.user, pk=pk,
                supplier=form.cleaned_data.get("supplier"), revision=form.cleaned_data["revision"],
                note=form.cleaned_data["note"], action=form.cleaned_data["action"])
            messages.success(request, "Décision de revue enregistrée.")
        except (ValidationError, OSError) as error:
            messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Le fichier archivé est indisponible.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("accounting:supplier_invoice_detail", pk=pk) if request.user.has_perm("accounting.view_supplierinvoice") else redirect("accounting:home")


@login_required
@permission_required("accounting.revalidate_supplierinvoice", raise_exception=True)
@require_POST
def revalidate(request, pk):
    get_object_or_404(SupplierInvoice, pk=pk, origin="PEPPOL")
    try:
        run = supplier_xml.revalidate_invoice(actor=request.user, pk=pk)
        messages.success(request, "Validation terminée : " + run.get_status_display())
    except (ValidationError, OSError) as error:
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Le fichier archivé est indisponible.")
    return redirect("accounting:supplier_invoice_detail", pk=pk) if request.user.has_perm("accounting.view_supplierinvoice") else redirect("accounting:home")


@login_required
@permission_required("accounting.download_supplierinvoice", raise_exception=True)
@require_GET
def download(request, pk):
    invoice = get_object_or_404(SupplierInvoice, pk=pk, origin="PEPPOL")
    try:
        data = supplier_xml.read_original(invoice)
    except (ValidationError, OSError):
        return HttpResponse("XML indisponible ou intégrité non garantie.", status=409, content_type="text/plain; charset=utf-8")
    response = HttpResponse(data, content_type="application/xml")
    response["Content-Disposition"] = f'attachment; filename="facture-fournisseur-{invoice.pk}.xml"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    audit(request.user, invoice, "XML fournisseur téléchargé", checksum=invoice.checksum)
    return response
