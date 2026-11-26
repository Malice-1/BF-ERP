from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from config.list_search import filter_rows
from config.party_quality import review_rows
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST, require_GET

from workflow.activity import write_log
from . import services, documents
from .customer_quality import customer_issues
from .forms import (CustomerForm, CustomerBillingForm, IssuerForm, TrainingForm, OrderForm, LineFormSet,
    PaymentForm, RevisionForm, ReversalForm, LINE_FIELDS)
from .models import (Customer, IssuerConfiguration, TrainingService, SalesOrder, SalesInvoice,
    SalesOrderLine, SalesInvoiceLine, InvoicePayment)


def form_error(form, error):
    for message in error.messages:
        form.add_error(None, message)


@login_required
@require_GET
def home(request):
    for permission, route in (("view_salesorder", "sales:orders"), ("view_salesinvoice", "sales:invoices"),
            ("view_customer", "sales:customers"), ("view_trainingservice", "sales:trainings"),
            ("add_salesorder", "sales:order_new"), ("add_customer", "sales:customer_new"),
            ("add_trainingservice", "sales:training_new"),
            ("change_issuerconfiguration", "sales:issuer"), ("view_salesreport", "sales:report")):
        if request.user.has_perm("sales." + permission):
            return redirect(route)
    return render(request, "sales/home.html")


@login_required
@permission_required("sales.view_customer", raise_exception=True)
@require_GET
def customers(request):
    rows = Customer.objects.all()
    rows, query = filter_rows(request, rows, {
        "name": ("Client", "name__icontains"), "code": ("Code", "code__icontains"),
        "vat": ("TVA", "vat_number__icontains"),
    })
    quality = request.GET.get("quality") == "1"
    context = {"rows": rows, "q": query, "quality": quality}
    if quality:
        context["review_rows"] = review_rows(rows, customer_issues)
    return render(request, "sales/customers.html", context)


@login_required
@require_http_methods(["GET", "POST"])
def customer_edit(request, pk=None):
    services.require(request.user, "change_customer" if pk else "add_customer")
    instance = get_object_or_404(Customer, pk=pk) if pk else Customer()
    form = CustomerForm(request.POST or None, instance=instance,
        can_bill=request.user.has_perm("sales.configure_customer_billing"))
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if pk:
                # Lock and preserve billing values for editors without billing rights.
                current = Customer.objects.select_for_update().get(pk=pk)
                for field in form.fields:
                    setattr(current, field, form.cleaned_data[field])
                current.full_clean()
                current.save()
            else:
                current = form.save()
            write_log(current, "updated" if pk else "created", {"fields": list(form.changed_data)}, "default", actor=request.user)
        messages.success(request, "Client enregistré.")
        return redirect("sales:customers" if request.user.has_perm("sales.view_customer") else "sales:home")
    return render(request, "sales/form.html", {"form": form, "title": "Modifier le client" if pk else "Nouveau client"})


@login_required
@permission_required("sales.configure_customer_billing", raise_exception=True)
@require_http_methods(["GET", "POST"])
def customer_billing(request, pk):
    instance = get_object_or_404(Customer, pk=pk)
    form = CustomerBillingForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            current = Customer.objects.select_for_update().get(pk=pk)
            for field in form.fields:
                setattr(current, field, form.cleaned_data[field])
            current.full_clean()
            current.save()
            write_log(current, "updated", {"billing_fields": form.changed_data}, "default", actor=request.user)
        messages.success(request, "Paramètres de facturation enregistrés.")
        return redirect("sales:home")
    return render(request, "sales/form.html", {"form": form, "title": f"Facturation — {instance.name}"})


@login_required
@permission_required("sales.change_issuerconfiguration", raise_exception=True)
@require_http_methods(["GET", "POST"])
def issuer(request):
    instance = IssuerConfiguration.objects.filter(pk=1).first() or IssuerConfiguration(pk=1)
    form = IssuerForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            IssuerConfiguration.objects.select_for_update().filter(pk=1).first()
            item = form.save()
            write_log(item, "updated", {"fields": form.changed_data}, "default", actor=request.user)
        messages.success(request, "Émetteur enregistré.")
        return redirect("sales:issuer")
    return render(request, "sales/form.html", {"form": form, "title": "Émetteur des factures"})


@login_required
@permission_required("sales.view_trainingservice", raise_exception=True)
@require_GET
def trainings(request):
    rows = TrainingService.objects.all()
    rows, query = filter_rows(request, rows, {
        "code": ("Code", "code__icontains"), "description": ("Description", "description__icontains"),
    })
    return render(request, "sales/trainings.html", {"rows": rows, "q": query})


@login_required
@require_http_methods(["GET", "POST"])
def training_edit(request, pk=None):
    services.require(request.user, "change_trainingservice" if pk else "add_trainingservice")
    item = get_object_or_404(TrainingService, pk=pk) if pk else TrainingService()
    form = TrainingForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            write_log(item, "updated" if pk else "created", {"fields": form.changed_data}, "default", actor=request.user)
        return redirect("sales:home")
    return render(request, "sales/form.html", {"form": form, "title": "Formation"})


def filtered(request, queryset, date_field):
    customer_lookup = "customer_snapshot__name__icontains" if date_field == "issue_date" else "customer__name__icontains"
    queryset, _ = filter_rows(request, queryset, {
        "number": ("Numéro", "number__icontains"), "customer": ("Client", customer_lookup),
    })
    customer = request.GET.get("customer", "")
    if customer.isdigit():
        queryset = queryset.filter(**{"order__customer_id" if date_field == "issue_date" else "customer_id": customer})
    for name, lookup in (("start", "gte"), ("end", "lte")):
        value = request.GET.get(name, "")
        if value:
            try:
                queryset = queryset.filter(**{f"{date_field}__{lookup}": date.fromisoformat(value)})
            except ValueError:
                messages.error(request, "Date de filtre invalide.")
    return queryset


@login_required
@permission_required("sales.view_salesorder", raise_exception=True)
@require_GET
def orders(request):
    rows = filtered(request, SalesOrder.objects.select_related("customer"), "order_date")
    if request.GET.get("status"):
        rows = rows.filter(status=request.GET["status"])
    return render(request, "sales/orders.html", {"rows": rows, "customers": Customer.objects.all(),
        "statuses": SalesOrder.Status.choices})


@login_required
@require_http_methods(["GET", "POST"])
def order_edit(request, pk=None):
    services.require(request.user, "change_salesorder" if pk else "add_salesorder")
    order = get_object_or_404(SalesOrder, pk=pk) if pk else SalesOrder()
    if order.status != "DRAFT":
        raise PermissionDenied("Cette commande n’est plus modifiable.")
    form = OrderForm(request.POST or None, instance=order)
    formset = LineFormSet(request.POST or None, instance=order)
    if request.method == "POST":
        valid_form, valid_lines = form.is_valid(), formset.is_valid()
        if valid_form and valid_lines:
            try:
                result = services.save_order(actor=request.user, pk=pk, revision=form.cleaned_data["revision"],
                    values={key: form.cleaned_data[key] for key in services.ORDER_FIELDS},
                    lines=[{key: line.cleaned_data[key] for key in LINE_FIELDS}
                        for line in formset.forms if line.cleaned_data and not line.cleaned_data.get("DELETE")])
            except ValidationError as error:
                form_error(form, error)
            else:
                messages.success(request, "Commande enregistrée en brouillon.")
                return redirect("sales:order_detail", pk=result.pk) if request.user.has_perm("sales.view_salesorder") else redirect("sales:home")
    return render(request, "sales/order_form.html", {"form": form, "formset": formset, "order": order,
        "training_data": list(TrainingService.objects.filter(is_active=True).values("id", "description", "unit"))})


@login_required
@permission_required("sales.view_salesorder", raise_exception=True)
@require_GET
def order_detail(request, pk):
    order = get_object_or_404(SalesOrder.objects.select_related("customer"), pk=pk)
    return render(request, "sales/order_detail.html", {"order": order, "lines": order.lines.all(),
        "revision_form": RevisionForm(initial={"revision": order.revision})})


@login_required
@require_POST
def order_action(request, pk, action):
    # Permissions must be checked before parsing input or exposing object existence.
    permission = {"confirm": "confirm_salesorder", "cancel": "cancel_salesorder", "invoice": "issue_salesinvoice"}.get(action)
    if permission is None:
        raise Http404
    services.require(request.user, permission)
    get_object_or_404(SalesOrder, pk=pk)
    form = RevisionForm(request.POST)
    if form.is_valid():
        try:
            if action == "invoice":
                invoice = services.issue_invoice(actor=request.user, pk=pk, revision=form.cleaned_data["revision"])
                if invoice.document_status == "DOCUMENT_ERROR":
                    messages.warning(request, "Facture émise ; la production documentaire doit être reprise.")
                else:
                    messages.success(request, "Facture émise et document archivé.")
                return redirect("sales:invoice_detail", pk=invoice.pk) if request.user.has_perm("sales.view_salesinvoice") else redirect("sales:home")
            services.transition(actor=request.user, pk=pk, revision=form.cleaned_data["revision"], action=action)
            messages.success(request, "Commande mise à jour.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    else:
        messages.error(request, "La révision de la commande est manquante ou invalide.")
    return redirect("sales:order_detail", pk=pk) if request.user.has_perm("sales.view_salesorder") else redirect("sales:home")


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_GET
def invoices(request):
    rows = filtered(request, SalesInvoice.objects.all(), "issue_date")
    for field in ("document_status", "payment_status", "invoice_format"):
        if request.GET.get(field):
            rows = rows.filter(**{field: request.GET[field]})
    return render(request, "sales/invoices.html", {"rows": rows, "customers": Customer.objects.all(),
        "document_statuses": SalesInvoice.DocumentStatus.choices, "payment_statuses": SalesInvoice.PaymentStatus.choices})


@login_required
@permission_required("sales.view_salesinvoice", raise_exception=True)
@require_GET
def invoice_detail(request, pk):
    invoice = get_object_or_404(SalesInvoice.objects.select_related("order"), pk=pk)
    accounting_entry = None
    if request.user.has_perm("accounting.view_journalentry"):
        from accounting.models import JournalEntry
        from accounting.sales_posting import SOURCE_KIND
        accounting_entry = JournalEntry.objects.filter(
            source_invoice=invoice, source_kind=SOURCE_KIND, source_identifier=str(invoice.pk)).first()
    return render(request, "sales/invoice_detail.html", {"invoice": invoice, "lines": invoice.lines.all(),
        "accounting_entry": accounting_entry,
        "documents": invoice.documents.prefetch_related("validations"),
        "payment_form": PaymentForm(), "payments": invoice.payments.select_related("reversal"),
        "paid": services.paid_amount(invoice), "balance": invoice.total - services.paid_amount(invoice)})


@login_required
@permission_required("sales.download_salesinvoice", raise_exception=True)
@require_GET
def download(request, pk, document_id):
    invoice = get_object_or_404(SalesInvoice, pk=pk)
    document = get_object_or_404(invoice.documents, pk=document_id)
    try:
        data = documents.read_document(document)
    except (ValidationError, OSError):
        return HttpResponse("Document indisponible ou intégrité non garantie.", status=409, content_type="text/plain; charset=utf-8")
    suffix = "xml" if document.document_type == "PEPPOL_XML" else "pdf"
    response = HttpResponse(data, content_type="application/xml" if suffix == "xml" else "application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{invoice.number}.{suffix}"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    services.event(invoice.order, request.user, "Document téléchargé", invoice=invoice, document=document.pk)
    return response


@login_required
@permission_required("sales.regenerate_salesinvoice", raise_exception=True)
@require_POST
def document_action(request, pk, action, document_id=None):
    get_object_or_404(SalesInvoice, pk=pk)
    try:
        if action == "regenerate":
            result = documents.regenerate(actor=request.user, pk=pk)
            if result:
                messages.success(request, "Document régénéré ; consultez son résultat de validation.")
            else:
                messages.error(request, "La production documentaire a échoué.")
        elif action == "validate":
            invoice = SalesInvoice.objects.get(pk=pk)
            get_object_or_404(invoice.documents, pk=document_id)
            documents.revalidate(actor=request.user, pk=pk, document_id=document_id)
            messages.success(request, "Validation terminée ; consultez son résultat.")
        else:
            raise Http404
    except (ValidationError, OSError) as error:
        messages.error(request, " ".join(error.messages) if isinstance(error, ValidationError) else "Document indisponible.")
    return redirect("sales:invoice_detail", pk=pk) if request.user.has_perm("sales.view_salesinvoice") else redirect("sales:home")


@login_required
@permission_required("sales.record_invoicepayment", raise_exception=True)
@require_POST
def payment(request, pk):
    get_object_or_404(SalesInvoice, pk=pk)
    form = PaymentForm(request.POST)
    if form.is_valid():
        try:
            services.record_payment(actor=request.user, pk=pk, **form.cleaned_data)
            messages.success(request, "Paiement enregistré.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    else:
        messages.error(request, str(form.errors.as_text()))
    return redirect("sales:invoice_detail", pk=pk) if request.user.has_perm("sales.view_salesinvoice") else redirect("sales:home")


@login_required
@permission_required("sales.record_invoicepayment", raise_exception=True)
@require_POST
def payment_reverse(request, pk, payment_id):
    get_object_or_404(InvoicePayment, pk=payment_id, invoice_id=pk)
    form = ReversalForm(request.POST)
    if form.is_valid():
        try:
            services.reverse_payment(actor=request.user, pk=pk, payment_id=payment_id, **form.cleaned_data)
            messages.success(request, "Paiement neutralisé ; son historique est conservé.")
        except ValidationError as error:
            messages.error(request, " ".join(error.messages))
    else:
        messages.error(request, "Un motif de correction est obligatoire.")
    return redirect("sales:invoice_detail", pk=pk) if request.user.has_perm("sales.view_salesinvoice") else redirect("sales:home")


@login_required
@permission_required("sales.view_salesreport", raise_exception=True)
@require_GET
def report(request):
    # Independent indicators: never add order commitments to invoices or payments.
    orders_qs = filtered(request, SalesOrder.objects.filter(status__in=["CONFIRMED", "INVOICED"]), "order_date")
    invoices_qs = filtered(request, SalesInvoice.objects.all(), "issue_date")
    line_orders = SalesOrderLine.objects.filter(order__in=orders_qs)
    line_invoices = SalesInvoiceLine.objects.filter(invoice__in=invoices_qs)
    from budgeting.models import CostCenter, Funding, BudgetProduct, Support
    dimensions = [("cost_center", "CDF", CostCenter), ("funding", "Financement", Funding),
        ("budget_product", "Produit budgétaire", BudgetProduct), ("support", "Support", Support)]
    for field, _, _ in dimensions:
        value = request.GET.get(field, "")
        if value.isdigit():
            line_orders = line_orders.filter(**{field + "_id": value})
            line_invoices = line_invoices.filter(**{field + "_id": value})
    payments = InvoicePayment.objects.filter(reversal__isnull=True)
    customer = request.GET.get("customer", "")
    if customer.isdigit():
        payments = payments.filter(invoice__order__customer_id=customer)
    for key, lookup in (("start", "gte"), ("end", "lte")):
        try:
            if request.GET.get(key):
                payments = payments.filter(**{f"payment_date__{lookup}": date.fromisoformat(request.GET[key])})
        except ValueError:
            pass
    group = request.GET.get("group", "cost_center")
    if group not in {d[0] for d in dimensions}:
        group = "cost_center"
    order_groups = {r[group + "_id"]: r["amount"] for r in line_orders.values(group + "_id").annotate(amount=Sum("subtotal"))}
    invoice_groups = {r[group + "_id"]: r["amount"] for r in line_invoices.values(group + "_id").annotate(amount=Sum("subtotal"))}
    model = next(d[2] for d in dimensions if d[0] == group)
    labels = {item.pk: str(item) for item in model.objects.all()}
    rows = [{"label": labels.get(pk, "Sans imputation"), "orders": order_groups.get(pk, 0),
        "invoices": invoice_groups.get(pk, 0)} for pk in sorted(set(order_groups) | set(invoice_groups), key=lambda p: (p is None, p or 0))]
    options = []
    for field, label, dimension_model in dimensions:
        items = list(dimension_model.objects.all())
        for item in items:
            item.sales_selected = request.GET.get(field) == str(item.pk)
        options.append((field, label, items))
    return render(request, "sales/report.html", {"rows": rows, "group": group,
        "customers": Customer.objects.all(), "dimensions": options,
        "ordered": line_orders.aggregate(value=Sum("subtotal"))["value"] or 0,
        "invoiced": line_invoices.aggregate(value=Sum("subtotal"))["value"] or 0,
        "received": payments.aggregate(value=Sum("amount"))["value"] or 0})
