from django import forms
from django.core import signing
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Max, Min, Sum, Count
from uuid import uuid4
from decimal import Decimal
from workflow.models import ConfigurationAuditEvent
from purchasing.flow import require
from purchasing.models import EnvelopeVersion, AnnualEnvelope
from .models import BudgetTransfer, BudgetTransferBatch
from . import transfers
from config import excel


def can_view_version_transfers(user):
    return any(user.has_perm(permission) for permission in (
        "budgeting.view_all_transfers", "budgeting.cancel_any_budgettransfer", "budgeting.decide_any_budgettransfer", "budgeting.view_budget_balances",
        "budgeting.view_envelopeversion", "budgeting.change_envelopeversion"))


def visible_transfers(user):
    rows = BudgetTransfer.objects.all()
    if can_view_version_transfers(user):
        return rows
    return rows.filter(
        Q(created_by=user) | Q(source_cdf__managers=user) |
        Q(destination_cdf__managers=user) | Q(steps__approved_by=user)
    ).distinct()


@login_required
@require_http_methods(["GET"])
def transfer_timeline(request, pk):
    transfer = get_object_or_404(visible_transfers(request.user), pk=pk)
    transfer = transfers.refresh(transfer.pk)
    steps = list(transfer.steps.select_related("approved_by"))
    return render(request, "budgeting/transfer_timeline.html", {
        "transfer": transfer,
        "steps": steps,
        "actionable_step_ids": [step.pk for step in steps
            if transfer.status == "pending" and step.state in ("pending", "unassigned")
            and transfers.can_decide(request.user, step)],
        "events": ConfigurationAuditEvent.objects.filter(
            object_type="budget_transfer", object_id=pk
        ).select_related("actor").order_by("created_at", "pk"),
    })


def export_transfers(rows, events=None):
    sheets = [("Transferts", ["Transfert", "Année", "Version", "Création", "Demandeur", "CDF source", "Financement source", "BI source", "Support source", "CDF destination", "Financement destination", "BI destination", "Support destination", "Support demandeur (historique)", "Montant TVAC", "État", "Justification"],
        ((str(t), t.envelope.year, t.budget_version.label, t.created_at, t.created_by, t.source_cdf, t.source_funding, t.source_product, t.source_support,
          t.destination_cdf, t.destination_funding, t.destination_product, t.destination_support, t.support, t.amount, t.get_status_display(), t.reason)
         for t in rows.select_related("envelope", "budget_version", "created_by", "source_cdf", "source_funding", "source_product", "source_support", "destination_cdf", "destination_funding", "destination_product", "destination_support", "support").iterator()))]
    if events is not None:
        sheets.append(("Historique", ["Date", "Transfert", "Auteur", "Événement", "Motif"],
            ((e.created_at, f"TB-{e.object_id}", e.actor, e.get_action_display(), e.payload.get("reason", "")) for e in events.iterator())))
    return excel.response("transferts-budgetaires", sheets)


class TransferForm(forms.ModelForm):
    budget_version = forms.ModelChoiceField(EnvelopeVersion.objects.filter(locked_at__isnull=True, deleted_at__isnull=True).select_related("envelope").order_by("-envelope__year", "-pk"), label="Version budgétaire")
    class Meta:
        model = BudgetTransfer
        fields = ["budget_version", "source_cdf", "source_funding", "source_product", "source_support", "destination_cdf", "destination_funding", "destination_product", "destination_support", "support", "amount", "reason"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in ("budget_version", "support", "destination_cdf", "destination_product", "destination_funding", "destination_support"):
                field.widget = forms.HiddenInput()
            else:
                field.widget.attrs["aria-label"] = field.label
        self.fields["reason"].widget.attrs["rows"] = 2

    def clean(self):
        data = super().clean()
        if data.get("amount") is not None and data["amount"] <= 0:
            self.add_error("amount", "Le montant doit être positif.")
        if all(data.get(f"{side}_{key}") for side in ("source", "destination") for key in ("cdf", "funding", "product")):
            if all(data[f"source_{key}"] == data[f"destination_{key}"] for key in ("cdf", "funding", "product")):
                raise ValidationError("La source et la destination doivent être différentes.")
        return data


class TransferHeaderForm(forms.Form):
    budget_version = TransferForm.base_fields["budget_version"]


class TransferCorrectionForm(forms.ModelForm):
    class Meta:
        model = BudgetTransfer
        fields = ["source_cdf", "source_product", "source_funding", "source_support",
                  "destination_cdf", "destination_product", "destination_funding", "destination_support", "amount", "reason"]


@login_required
@require_http_methods(["GET", "POST"])
def transfer_correct(request, pk):
    require(request.user, "budgeting.add_budgettransfer")
    transfer = get_object_or_404(BudgetTransfer, pk=pk, created_by=request.user)
    if transfer.status != "returned":
        raise PermissionDenied
    form = TransferCorrectionForm(request.POST or None, instance=transfer)
    error = None
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                locked = BudgetTransfer.objects.select_for_update().get(pk=pk)
                if locked.status != "returned" or locked.revision != int(request.POST.get("revision", "-1")):
                    raise ValidationError("La transaction a changé. Rechargez la page.")
                AnnualEnvelope.objects.select_for_update().get(pk=locked.envelope_id)
                version = EnvelopeVersion.objects.select_for_update().get(pk=locked.budget_version_id)
                transfers.ensure_writable(version)
                corrected = TransferCorrectionForm(request.POST, instance=locked)
                before = {name: str(getattr(locked, name)) for name in TransferCorrectionForm.Meta.fields}
                if not corrected.is_valid():
                    raise ValidationError("Vérifiez les informations saisies.")
                corrected.save()
                transfers.audit(locked, request.user, "transfer.correct", before=before,
                    after={name: str(getattr(locked, name)) for name in TransferCorrectionForm.Meta.fields})
                transfers.act(pk=pk, actor=request.user, revision=locked.revision, action="submit")
            return redirect("transfer_detail", pk=pk)
        except (ValidationError, ValueError) as exc:
            error = " · ".join(exc.messages) if isinstance(exc, ValidationError) else "Révision invalide."
    return render(request, "budgeting/transfer_correct.html", {"transfer": transfer, "form": form, "error": error})


class TransferDestinationForm(forms.Form):
    destination_cdf = TransferForm.base_fields["destination_cdf"]
    destination_product = TransferForm.base_fields["destination_product"]
    destination_funding = TransferForm.base_fields["destination_funding"]
    destination_support = forms.ModelChoiceField(BudgetTransfer._meta.get_field("destination_support").remote_field.model.objects.all(), label="Support", required=False)


TransferFormSet = forms.formset_factory(TransferForm, extra=0, min_num=1, validate_min=True,
                                      max_num=100, validate_max=True, absolute_max=100, can_delete=True)


@login_required
@require_http_methods(["GET", "POST"])
def transfer_list(request):
    if not request.user.has_perms(["budgeting.view_all_transfers"]) and not request.user.has_perm("budgeting.add_budgettransfer"):
        raise PermissionDenied
    selected = request.GET.get("version", "")
    can_create = request.user.has_perm("budgeting.add_budgettransfer")
    submission_errors = []
    if request.method == "GET" and not can_create and not excel.requested(request):
        return redirect("transfer_monitor")
    data = request.POST.copy() if request.method == "POST" else None
    shared_destination = data is None or data.get("shared_destination") == "1"
    # Accept previously opened single-transfer forms during the UI transition.
    if data is not None and "lines-TOTAL_FORMS" not in data:
        data["lines-TOTAL_FORMS"], data["lines-INITIAL_FORMS"] = "1", "0"
        for name in TransferForm.base_fields:
            data[f"lines-0-{name}"] = data.get(name, "")
    header = TransferHeaderForm(data, initial={"budget_version": selected})
    destination = TransferDestinationForm(data if shared_destination else None)
    if data is not None:
        # Common fields are authoritative for every row.
        try:
            row_count = max(0, min(100, int(data.get("lines-TOTAL_FORMS", "0"))))
        except ValueError:
            row_count = 0
        for index in range(row_count):
            populated = any(data.get(f"lines-{index}-{name}", "").strip() for name in ("source_cdf", "source_product", "source_funding", "source_support", "amount", "reason"))
            common_fields = ("budget_version", *TransferDestinationForm.base_fields) if shared_destination else ("budget_version",)
            for name in common_fields:
                data[f"lines-{index}-{name}"] = data.get(name, "") if populated else ""
    formset = TransferFormSet(data, prefix="lines")
    for line in [*formset.forms, formset.empty_form]:
        line.fields["support"].queryset = request.user.supports.all()
    if request.method == "POST":
        require(request.user, "budgeting.add_budgettransfer")
        header_valid = header.is_valid()
        destination_valid = destination.is_valid() if shared_destination else True
        lines_valid = formset.is_valid()
        if header_valid and destination_valid and lines_valid:
            created = []
            try:
                with transaction.atomic():
                    version = header.cleaned_data["budget_version"]
                    AnnualEnvelope.objects.select_for_update().get(pk=version.envelope_id)
                    version = EnvelopeVersion.objects.select_for_update().get(pk=version.pk)
                    transfers.ensure_writable(version)
                    batch_id = uuid4()
                    for line in formset:
                        if not line.cleaned_data or line.cleaned_data.get("DELETE"):
                            continue
                        transfer = line.save(commit=False)
                        transfer.batch_id = batch_id
                        transfer.created_by = request.user
                        transfer.budget_version = version
                        transfer.save()
                        transfers.audit(transfer, request.user, "created")
                        transfers.act(pk=transfer.pk, actor=request.user, revision=transfer.revision, action="submit")
                        created.append(transfer)
                if len(created) == 1:
                    return redirect("transfer_detail", pk=created[0].pk)
                messages.success(request, f"{len(created)} transferts soumis pour validation.")
                return redirect("transfer_monitor")
            except ValidationError as exc:
                submission_errors = exc.messages
    destination_total = sum((line.cleaned_data.get("amount") or Decimal(0) for line in formset if hasattr(line, "cleaned_data") and not line.cleaned_data.get("DELETE")), Decimal(0))
    if excel.requested(request):
        rows = BudgetTransfer.objects.all() if request.user.has_perm("budgeting.view_all_transfers") else BudgetTransfer.objects.filter(created_by=request.user)
        return export_transfers(rows.order_by("-pk"))
    return render(request, "budgeting/transfers.html", {"header": header, "formset": formset, "destination": destination, "destination_total": destination_total, "can_create": can_create, "submission_errors": submission_errors})


@login_required
@require_http_methods(["GET"])
def version_transfers(request, version_id):
    financial = can_view_version_transfers(request.user)
    if not financial and not request.user.has_perm("budgeting.add_budgettransfer"):
        raise PermissionDenied
    version = get_object_or_404(EnvelopeVersion.objects.select_related("envelope"), pk=version_id)
    rows = BudgetTransfer.objects.filter(budget_version=version).select_related(
        "created_by", "source_cdf", "destination_cdf").order_by("-created_at", "-pk")
    if not financial:
        rows = rows.filter(created_by=request.user)
    events = ConfigurationAuditEvent.objects.filter(object_type="budget_transfer", object_id__in=rows.values("pk")).select_related("actor").order_by("created_at", "pk")
    if excel.requested(request):
        return export_transfers(rows, events)
    return render(request, "budgeting/version_transfers.html", {"version": version, "transfers": rows,
        "events": events, "financial": financial})


@login_required
@require_http_methods(["GET", "POST"])
def transfer_detail(request, pk):
    transfer = get_object_or_404(BudgetTransfer, pk=pk)
    if not visible_transfers(request.user).filter(pk=pk).exists():
        raise PermissionDenied
    error = None
    if request.method == "POST":
        try:
            transfers.act(pk=pk, actor=request.user, revision=int(request.POST.get("revision", "-1")), action=request.POST.get("action"), step_id=request.POST.get("step_id"), reason=request.POST.get("reason", ""))
            return redirect("transfer_detail", pk=pk)
        except (ValidationError, ValueError) as exc:
            error = " · ".join(exc.messages) if isinstance(exc, ValidationError) else "Révision invalide."
    transfer = transfers.refresh(pk)
    rows = [{"step": step, "actionable": True} for step in transfer.steps.all()
            if transfer.status == "pending" and step.state in ("pending", "unassigned")
            and transfers.can_decide(request.user, step)]
    return render(request, "budgeting/transfer.html", {"transfer": transfer, "rows": rows, "error": error,
        "can_cancel": transfers.can_cancel(request.user, transfer),
        "cancellation_requires_reason": request.user.has_perm("budgeting.cancel_any_budgettransfer"),
        }, status=409 if error else 200)


@login_required
@require_http_methods(["POST"])
def transfer_batch_approve(request, pk):
    require(request.user, "budgeting.decide_any_budgettransfer")
    get_object_or_404(BudgetTransferBatch, pk=pk)
    try:
        snapshot = signing.loads(request.POST.get("snapshot", ""), salt="transfer-batch-approval")
        if snapshot.get("batch") != pk:
            raise signing.BadSignature
        count = transfers.approve_batch(batch_pk=pk, actor=request.user, revisions=snapshot["revisions"])
    except (signing.BadSignature, KeyError, TypeError, AttributeError):
        messages.error(request, "La demande de validation est invalide. Rechargez la liste.")
    except ValidationError as exc:
        messages.error(request, " · ".join(exc.messages))
    else:
        messages.success(request, f"Transfert {pk} accompli : {count} ligne(s) validée(s).")
    return redirect("transfer_monitor")


@login_required
@require_http_methods(["POST"])
def transfer_batch_close(request, pk):
    action = request.POST.get("action")
    if action not in ("return_batch", "cancel_batch"):
        raise PermissionDenied
    require(request.user, "budgeting.decide_any_budgettransfer" if action == "return_batch" else "budgeting.cancel_any_budgettransfer")
    get_object_or_404(BudgetTransferBatch, pk=pk)
    try:
        snapshot = signing.loads(request.POST.get("snapshot", ""), salt="transfer-batch-approval")
        if snapshot.get("batch") != pk:
            raise signing.BadSignature
        count = transfers.close_batch(batch_pk=pk, actor=request.user, revisions=snapshot["revisions"],
            action="return" if action == "return_batch" else "cancel", reason=request.POST.get("reason", ""))
    except (signing.BadSignature, KeyError, TypeError, AttributeError):
        messages.error(request, "La demande est invalide. Rechargez la liste.")
    except ValidationError as exc:
        messages.error(request, " · ".join(exc.messages))
    else:
        result = "renvoyée(s) au demandeur pour correction" if action == "return_batch" else "définitivement annulée(s)"
        messages.success(request, f"Transfert {pk} : {count} ligne(s) {result}.")
    return redirect("transfer_monitor")


@login_required
@require_http_methods(["GET"])
def transfer_monitor(request):
    if not (can_view_version_transfers(request.user) or request.user.has_perm("budgeting.add_budgettransfer") or request.user.managed_cost_centers.exists() or visible_transfers(request.user).exists()):
        raise PermissionDenied
    rows = visible_transfers(request.user).select_related("envelope", "budget_version", "created_by",
        "source_cdf", "source_product", "source_funding", "destination_cdf", "destination_product", "destination_funding").order_by("-pk")
    status = request.GET.get("status", "")
    year = request.GET.get("year", "")
    version_id = request.GET.get("version", "")
    number = request.GET.get("number", "").strip()
    if number:
        if number.isascii() and number.isdigit() and len(number) <= 18:
            rows = rows.filter(batch_id__in=BudgetTransferBatch.objects.filter(pk=int(number)).values("key"))
        else:
            rows = rows.none()
    if status in dict(BudgetTransfer._meta.get_field("status").choices):
        rows = rows.filter(status=status)
    if year.isdigit() and len(year) == 4:
        rows = rows.filter(envelope__year=int(year))
    if version_id.isdigit() and len(version_id) <= 18:
        rows = rows.filter(budget_version_id=int(version_id))
    if excel.requested(request):
        return export_transfers(rows)
    groups = BudgetTransfer.objects.filter(pk__in=rows.values("pk")).order_by().values("batch_id").annotate(
        latest=Max("pk"), reference=Min("pk"), total=Sum("amount"), line_count=Count("pk", distinct=True)
    ).order_by("-latest")
    page = Paginator(groups, 50).get_page(request.GET.get("page"))
    batches = list(page)
    by_id = {group["batch_id"]: group for group in batches}
    numbers = dict(BudgetTransferBatch.objects.filter(key__in=by_id).values_list("key", "pk"))
    for group in batches:
        group["number"] = numbers[group["batch_id"]]
        group["lines"] = []
    for item in rows.filter(batch_id__in=by_id).order_by("pk"):
        item.decision_step = None
        if item.status == "pending":
            current = transfers.refresh(item.pk)
            item.status, item.revision = current.status, current.revision
            if current.status == "pending":
                item.decision_step = next((step for step in current.steps.all()
                    if step.state in ("pending", "unassigned")
                    and transfers.can_decide(request.user, step)), None)
        group = by_id[item.batch_id]
        group["lines"].append(item)
        if "first" not in group:
            group["first"] = item
    page.object_list = batches
    states_by_batch = {key: set() for key in by_id}
    revisions_by_batch = {key: {} for key in by_id}
    for key, state, pk, revision in BudgetTransfer.objects.filter(batch_id__in=by_id).values_list("batch_id", "status", "pk", "revision"):
        states_by_batch[key].add(state)
        revisions_by_batch[key][str(pk)] = revision
    for group in batches:
        states = states_by_batch[group["batch_id"]]
        group["status"], group["status_label"] = transfers.batch_status(states)
        group["can_approve_all"] = (request.user.has_perm("budgeting.decide_any_budgettransfer")
            and "pending" in states and states <= {"pending", "approved"})
        group["can_return_all"] = (request.user.has_perm("budgeting.decide_any_budgettransfer")
            and "cancelled" not in states and states not in ({"returned"}, {"approved"}))
        group["can_cancel_all"] = (request.user.has_perm("budgeting.cancel_any_budgettransfer") and states != {"cancelled"})
        if group["can_approve_all"] or group["can_return_all"] or group["can_cancel_all"]:
            group["snapshot"] = signing.dumps({"batch": group["number"],
                "revisions": revisions_by_batch[group["batch_id"]]}, salt="transfer-batch-approval", compress=True)
    return render(request, "budgeting/transfer_monitor.html", {
        "page": page, "status": status, "year": year, "number": number,
        "selected_version": version_id, "versions": EnvelopeVersion.objects.filter(pk__in=visible_transfers(request.user).values("budget_version_id")).select_related("envelope").order_by("-envelope__year", "-pk"),
        "statuses": BudgetTransfer._meta.get_field("status").choices})
