from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django import forms
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from suppliers.models import Supplier
from .models import SupplierInvoice, AccountingEvent
from . import supplier_xml
from .services import audit


class UploadForm(forms.Form):
    file = forms.FileField(label="Facture fournisseur XML Peppol", widget=forms.ClearableFileInput(attrs={"accept": ".xml,application/xml,text/xml"}))


class ReviewForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    supplier = forms.ModelChoiceField(label="Fournisseur existant", queryset=Supplier.objects.all(), required=False)
    note = forms.CharField(label="Justification de revue / rejet", max_length=2000, widget=forms.Textarea(attrs={"rows": 3}))
    action = forms.ChoiceField(label="Décision", choices=[("approve", "Approuver"), ("reject", "Rejeter")])


@login_required
@permission_required("accounting.view_supplierinvoice", raise_exception=True)
@require_GET
def invoice_list(request):
    rows = SupplierInvoice.objects.select_related("supplier").prefetch_related("validations")
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(Q(invoice_number__icontains=query) | Q(extracted_data__seller__name__icontains=query) | Q(supplier__name__icontains=query))
    if request.GET.get("status") in ("RECEIVED", "REVIEWED", "REJECTED"):
        rows = rows.filter(status=request.GET["status"])
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
    return render(request, "accounting/form.html", {"form": form, "title": "Importer une facture fournisseur XML",
        "intro": "Facture UBL Invoice, Peppol BIS Billing 3.0, type 380. Taille maximale : 5 Mo par défaut. Le fichier original est archivé ; les données seront à vérifier. Aucun compte ou calcul de déductibilité TVA n’est choisi automatiquement."})


@login_required
@permission_required("accounting.view_supplierinvoice", raise_exception=True)
@require_GET
def detail(request, pk):
    invoice = get_object_or_404(SupplierInvoice.objects.select_related("supplier"), pk=pk)
    candidates = supplier_xml.supplier_candidates(invoice)
    initial = {"revision": invoice.revision}
    if len(candidates) == 1:
        initial["supplier"] = candidates[0].pk
    return render(request, "accounting/supplier_invoice_detail.html", {"invoice": invoice,
        "latest": invoice.validations.first(), "runs": invoice.validations.all(),
        "events": AccountingEvent.objects.filter(object_type=invoice._meta.label_lower, object_identifier=str(invoice.pk)),
        "review_form": ReviewForm(initial=initial), "candidates": candidates})


@login_required
@permission_required("accounting.review_supplierinvoice", raise_exception=True)
@require_POST
def review(request, pk):
    get_object_or_404(SupplierInvoice, pk=pk)
    form = ReviewForm(request.POST)
    if form.is_valid():
        try:
            supplier_xml.review_invoice(actor=request.user, pk=pk, **form.cleaned_data)
            messages.success(request, "Décision de revue enregistrée. Aucune écriture comptable automatique n’a été créée.")
        except (ValidationError, OSError) as error:
            messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Le fichier archivé est indisponible.")
    else:
        messages.error(request, form.errors.as_text())
    return redirect("accounting:supplier_invoice_detail", pk=pk) if request.user.has_perm("accounting.view_supplierinvoice") else redirect("accounting:home")


@login_required
@permission_required("accounting.revalidate_supplierinvoice", raise_exception=True)
@require_POST
def revalidate(request, pk):
    get_object_or_404(SupplierInvoice, pk=pk)
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
    invoice = get_object_or_404(SupplierInvoice, pk=pk)
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
