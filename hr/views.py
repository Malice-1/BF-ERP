from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.debug import sensitive_post_parameters

from workflow.activity import write_log
from .forms import EmployeeForm, PayrollForm
from .models import Employee, PayrollDetails


def save_form(form, actor):
    if not form.is_valid():
        return False
    if form.cleaned_data["revision"] != form.instance.revision:
        form.add_error(None, "Cette fiche a changé. Rechargez la page avant de réessayer.")
        return False
    record = form.save(commit=False)
    created = record._state.adding
    record.revision += 1
    record.save()
    write_log(record, "created" if created else "updated", {}, record._state.db, actor=actor)
    return True


@never_cache
@login_required
@permission_required("hr.view_employee", raise_exception=True)
@require_GET
def employees(request):
    rows = Employee.objects.all()
    query = request.GET.get("q", "").strip()
    for term in query.split():
        rows = rows.filter(Q(number__icontains=term) | Q(first_name__icontains=term)
                           | Q(last_name__icontains=term) | Q(department__icontains=term))
    status = request.GET.get("status")
    if status in ("active", "inactive"):
        rows = rows.filter(is_active=status == "active")
    template = ("hr/employee_results.html" if request.headers.get("X-Requested-With") == "XMLHttpRequest"
                else "hr/employees.html")
    return render(request, template, {
        "page": Paginator(rows, 50).get_page(request.GET.get("page")), "query": query, "status": status,
    })


@never_cache
@login_required
@permission_required("hr.view_employee", raise_exception=True)
@require_GET
def employee_detail(request, pk):
    return render(request, "hr/employee.html", {"employee": get_object_or_404(Employee, pk=pk)})


@never_cache
@login_required
@permission_required("hr.view_employee", raise_exception=True)
@require_http_methods(["GET", "POST"])
@transaction.atomic
def employee_edit(request, pk=None):
    if not request.user.has_perm("hr.change_employee" if pk else "hr.add_employee"):
        raise PermissionDenied
    records = Employee.objects.select_for_update() if request.method == "POST" else Employee.objects
    employee = get_object_or_404(records, pk=pk) if pk else Employee()
    form = EmployeeForm(request.POST if request.method == "POST" else None, instance=employee,
                        initial={"revision": employee.revision})
    if request.method == "POST" and save_form(form, request.user):
        messages.success(request, "Fiche employé enregistrée.")
        return redirect("hr:employee_detail", pk=form.instance.pk)
    return render(request, "hr/form.html", {"form": form, "employee": employee,
        "title": "Modifier la fiche employé" if pk else "Nouvel employé"})


@never_cache
@login_required
@permission_required(("hr.view_employee", "hr.view_payrolldetails"), raise_exception=True)
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters("iban", "gross_amount", "work_percentage", "frequency", "effective_date")
@transaction.atomic
def payroll(request, pk):
    can_edit = request.user.has_perm("hr.change_payrolldetails")
    if request.method == "POST" and not can_edit:
        raise PermissionDenied
    records = Employee.objects.select_for_update() if request.method == "POST" else Employee.objects
    employee = get_object_or_404(records, pk=pk)
    record = PayrollDetails.objects.filter(employee=employee).first()
    form = None
    if can_edit:
        instance = record or PayrollDetails(employee=employee)
        form = PayrollForm(request.POST if request.method == "POST" else None, instance=instance,
                           initial={"revision": instance.revision})
        if request.method == "POST" and save_form(form, request.user):
            messages.success(request, "Données de paie enregistrées.")
            return redirect("hr:payroll", pk=pk)
    return render(request, "hr/payroll.html", {"employee": employee, "payroll": record, "form": form})
