from accounts.admin_deletion import SystemModelAdmin
from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_http_methods
from config import excel

from .models import CostCenter, Funding, Support, Subproject, Section, BudgetProduct, Budget, BudgetLine, TrainingActivity
from purchasing.models import DetailedProduct
from accounts.admin import ReadOnlyAdmin
from .forms import CostCenterAdminForm, SupportAdminForm, CostCenterManagersField
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import path
from . import history_archive_admin  # noqa: F401
from .reference_import import CostCenterImportForm, FundingImportForm, REFERENCE_HEADERS


@admin.register(TrainingActivity)
class TrainingActivityAdmin(SystemModelAdmin):
    list_display = ("month", "training", "cost_center", "trainees", "hours", "sessions")
    list_filter = ("month", "cost_center")
    search_fields = ("training__code", "training__description")
    ordering = ("-month", "training__code")


class ManagedReferenceAdmin(SystemModelAdmin):
    form = CostCenterAdminForm
    list_display = (
        "code",
        "label",
        "responsables",
    )

    search_fields = (
        "code",
        "label",
    )

    def get_urls(self):
        return [path("responsables/", self.admin_site.admin_view(self.manager_choices),
                     name=f"budgeting_{self.model._meta.model_name}_manager_choices")] + super().get_urls()

    def manager_choices(self, request):
        if not (request.user.has_perm("budgeting.manage_cost_center_managers")
                and (self.has_add_permission(request) or self.has_change_permission(request))):
            raise PermissionDenied
        users = get_user_model().objects.filter(is_active=True).order_by("username")
        for term in request.GET.get("term", "").split():
            users = users.filter(Q(username__icontains=term) | Q(first_name__icontains=term)
                                 | Q(last_name__icontains=term))
        page = Paginator(users, 20).get_page(request.GET.get("page", 1))
        field = CostCenterManagersField(queryset=users)
        return JsonResponse({"results": [{"id": str(user.pk), "text": field.label_from_instance(user)}
                                         for user in page],
                             "pagination": {"more": page.has_next()}})

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("managers")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not request.user.has_perm("budgeting.manage_cost_center_managers"):
            return (*fields, "managers")
        return fields

    @admin.display(description="Responsables")
    def responsables(self, obj):
        return ", ".join(user.get_full_name().strip() or user.username
                         for user in obj.managers.all()) or "—"

class ReferenceExcelAdminMixin:
    list_filter = ("is_active",)
    search_fields = ("code", "label")
    export_headers = REFERENCE_HEADERS

    def get_urls(self):
        return [
            path("import-excel/", self.admin_site.admin_view(require_http_methods(["GET", "POST"])(self.import_excel)),
                 name=f"budgeting_{self.model._meta.model_name}_import_excel"),
            path("export-excel/", self.admin_site.admin_view(require_GET(self.export_excel)),
                 name=f"budgeting_{self.model._meta.model_name}_export_excel"),
        ] + super().get_urls()

    def export_row(self, item):
        return item.code, item.label, "Actif" if item.is_active else "Inactif"

    def export_excel(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        try:
            centers = self.get_changelist_instance(request).queryset
        except IncorrectLookupParameters:
            return HttpResponseBadRequest("Les filtres de la liste sont invalides.")
        rows = (self.export_row(item) for item in centers.iterator(chunk_size=500))
        return excel.response(self.filename, [(self.sheet_name, self.export_headers, rows)])

    def import_excel(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method == "GET" and request.GET.get("patron") == "1":
            return excel.response(f"patron-{self.filename}", [(self.sheet_name, self.import_form.headers, ())])
        form = self.import_form(request.POST, request.FILES) if request.method == "POST" else self.import_form()
        if request.method == "POST" and form.is_valid():
            centers = form.cleaned_data["file"]
            if (any(manager is not None for _, manager in centers)
                    and not request.user.has_perm("budgeting.manage_cost_center_managers")):
                raise PermissionDenied
            try:
                with transaction.atomic():
                    for center, manager in centers:
                        center.save(force_insert=True)
                        if manager is not None:
                            center.managers.add(manager)
                        self.log_addition(request, center, "Import Excel")
            except IntegrityError:
                form.add_error("file", "Impossible de terminer l’import. Vérifiez les données, puis réessayez.")
            else:
                self.message_user(request, f"{self.sheet_name} créés : {len(centers)}.", messages.SUCCESS)
                return redirect(f"{self.admin_site.name}:budgeting_{self.model._meta.model_name}_changelist")
        return render(request, f"admin/budgeting/{self.model._meta.model_name}/import_excel.html", {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Importer des {self.model._meta.verbose_name_plural} depuis Excel",
            "form": form,
        })


@admin.register(CostCenter)
class CostCenterAdmin(ReferenceExcelAdminMixin, ManagedReferenceAdmin):
    list_display = (*ManagedReferenceAdmin.list_display, "is_active")
    change_list_template = "admin/budgeting/costcenter/change_list.html"
    import_form = CostCenterImportForm
    filename = "cdf"
    sheet_name = "CDF"
    export_headers = (*REFERENCE_HEADERS, "Responsables")

    def export_row(self, item):
        return (*super().export_row(item), ", ".join(sorted(manager.username for manager in item.managers.all())))


@admin.register(Support)
class SupportAdmin(ManagedReferenceAdmin):
    form = SupportAdminForm


@admin.register(Funding)
class FundingAdmin(ReferenceExcelAdminMixin, SystemModelAdmin):
    exclude = ("managers",)
    list_display = (
        "code",
        "label",
        "is_active",
    )

    import_form = FundingImportForm
    filename = "financements"
    sheet_name = "Financements"
    change_list_template = "admin/budgeting/funding/change_list.html"


@admin.register(BudgetProduct, Subproject, Section)
class BudgetReferenceAdmin(SystemModelAdmin):
    list_display = (
        "code",
        "label",
    )

    search_fields = (
        "code",
        "label",
    )


@admin.register(Budget)
class BudgetAdmin(ReadOnlyAdmin):
    list_display = (
        "code",
        "year",
        "is_active",
    )

    search_fields = (
        "code",
        "year",
        "is_active",
    )



@admin.register(BudgetLine)
class BudgetLineAdmin(ReadOnlyAdmin):
    list_display = (
        "budget",
        "cost_center",
        "funding",
        "budget_product",
        "allocated_amount",
        "committed_amount",
        "consumed_amount",
    )

    search_fields = (
        "budget__code",
        "cost_center__code",
        "funding__code",
        "budget_product__code",
    )


@admin.register(DetailedProduct)
class DetailedProductAdmin(SystemModelAdmin):

    list_display = (
        "code",
        "label",
        "budget_product",
    )

    search_fields = (
        "code",
        "label",
        "budget_product__code",
    )

    list_filter = (
        "budget_product",
    )
