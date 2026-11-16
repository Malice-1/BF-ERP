from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods


@login_required
@permission_required("budgeting.manage_cost_center_managers", raise_exception=True)
@require_http_methods(["GET", "POST"])
def retired_manager_editor(request, pk=None):
    if request.method == "POST":
        return HttpResponse("Les affectations datées ne sont plus utilisées. Gérez les responsables depuis Configuration → CDF ou Supports.", status=410)
    return redirect("entity_managers")


@login_required
@permission_required("budgeting.manage_cost_center_managers", raise_exception=True)
@require_http_methods(["GET", "POST"])
def entity_managers(request):
    from django.db import transaction
    from django.contrib import messages
    from .forms import EntityManagersForm
    from .models import CostCenter, Support
    from workflow.models import ConfigurationAuditEvent

    form = EntityManagersForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        model = CostCenter if form.cleaned_data["kind"] == "cdf" else Support
        with transaction.atomic():
            entity = get_object_or_404(model.objects.select_for_update(), pk=form.cleaned_data["entity_id"])
            before = list(entity.managers.values_list("pk", flat=True))
            entity.managers.set(form.cleaned_data["managers"])
            ConfigurationAuditEvent.objects.create(actor=request.user, action="managers.updated",
                object_type=entity._meta.model_name, object_id=entity.pk,
                payload={"before": before, "after": list(entity.managers.values_list("pk", flat=True))})
        messages.success(request, "Responsables enregistrés.")
        return redirect("entity_managers")
    rows = []
    for kind, model in [("cdf", CostCenter), ("support", Support)]:
        for entity in model.objects.prefetch_related("managers"):
            rows.append({"entity": entity, "kind": kind, "form": EntityManagersForm(initial={
                "kind": kind, "entity_id": entity.pk, "managers": list(entity.managers.all())})})
    return render(request, "budgeting/entity_managers.html", {"rows": rows, "form": form})
