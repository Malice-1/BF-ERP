from accounts.admin_deletion import SystemModelAdmin
from django.contrib import admin

from .models import CostCenter, Funding, Support, Subproject, Section, BudgetProduct, Budget, BudgetLine, TrainingActivity
from purchasing.models import DetailedProduct
from accounts.admin import ReadOnlyAdmin
from .forms import CostCenterAdminForm, SupportAdminForm, CostCenterManagersField
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.urls import path


@admin.register(TrainingActivity)
class TrainingActivityAdmin(SystemModelAdmin):
    list_display = ("month", "training", "cost_center", "trainees", "hours", "sessions")
    list_filter = ("month", "cost_center")
    search_fields = ("training__code", "training__description")
    ordering = ("-month", "training__code")


@admin.register(CostCenter)
class CostCenterAdmin(SystemModelAdmin):
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

@admin.register(Support)
class SupportAdmin(CostCenterAdmin):
    form = SupportAdminForm


@admin.register(Funding)
class FundingAdmin(SystemModelAdmin):
    exclude = ("managers",)
    list_display = (
        "code",
        "label",
    )

    search_fields = (
        "code",
        "label",
    )


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
