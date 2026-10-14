from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .forms import ManagerAssignmentForm, EndManagerAssignmentForm
from .models import CostCenterManagerAssignment
from .services import assign_cost_center_manager, end_cost_center_manager_assignment


@login_required
@permission_required("budgeting.manage_cost_center_managers", raise_exception=True)
@require_http_methods(["GET"])
def manager_list(request):
    return render(request, "budgeting/managers.html", {"assignments": CostCenterManagerAssignment.objects.select_related("cost_center", "user")})


@login_required
@permission_required("budgeting.manage_cost_center_managers", raise_exception=True)
@require_http_methods(["GET", "POST"])
def manager_edit(request, pk=None):
    if pk:
        get_object_or_404(CostCenterManagerAssignment, pk=pk)
    form_class = EndManagerAssignmentForm if pk else ManagerAssignmentForm
    form = form_class(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            if pk:
                end_cost_center_manager_assignment(actor=request.user, assignment_id=pk, **form.cleaned_data)
            else:
                assign_cost_center_manager(actor=request.user, **form.cleaned_data)
            return redirect("managers")
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
    return render(request, "purchasing/form.html", {"title": "Clôturer une affectation CDF" if pk else "Affecter un responsable CDF", "form": form})
