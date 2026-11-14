from accounts.admin_deletion import SystemModelAdmin
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import (Submission, LineSnapshot, ApprovalStep, PurchaseOrder,
    Delegation, PurchaseNotice)
from accounts.admin import ReadOnlyAdmin
from .flow import activate_envelope
from budgeting.models import AnnualEnvelope, EnvelopeVersion, Allocation, BudgetEntry


class FrenchFields:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        labels = {"label": "Libellé", "envelope": "Enveloppe annuelle", "year": "Année",
            "cost_center": "CDF", "funding": "Financement", "budget_product": "Produit budgétaire",
            "amount": "Allocation TVAC (EUR)"}
        if field is not None and db_field.name in labels:
            field.label = labels[db_field.name]
        return field


class DraftInline(FrenchFields, admin.TabularInline):
    extra = 0

    def has_add_permission(self, request, obj=None):
        return (obj is None or not obj.published_at) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return (obj is None or not obj.published_at) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_active and request.user.is_superuser:
            return True
        return (obj is None or not obj.published_at) and super().has_delete_permission(request, obj)


class AllocationInline(DraftInline):
    model = Allocation


class PublishedAdmin(FrenchFields, SystemModelAdmin):
    readonly_fields = ("published_at",)

    def has_change_permission(self, request, obj=None):
        return (obj is None or not obj.published_at) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if request.user.is_active and request.user.is_superuser:
            return True
        return (obj is None or not obj.published_at) and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            current = type(obj).objects.select_for_update().get(pk=obj.pk)
            if current.published_at:
                raise ValidationError("Version publiée immuable. Rechargez la page.")
        super().save_model(request, obj, form, change)

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm(f"{self.model._meta.app_label}.view_{self.model._meta.model_name}")


@admin.register(AnnualEnvelope)
class EnvelopeAdmin(FrenchFields, SystemModelAdmin):
    list_display = ("year", "active_version")
    readonly_fields = ("active_version",)

    def has_change_permission(self, request, obj=None):
        return (obj is None or not obj.versions.exists()) and super().has_change_permission(request, obj)


@admin.register(EnvelopeVersion)
class BudgetVersionAdmin(PublishedAdmin):
    list_display = ("label", "envelope", "published_at")
    inlines = [AllocationInline]
    actions = ["activate", "clone"]

    @admin.action(description="Publier et activer la version sélectionnée", permissions=["change"])
    def activate(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "Sélectionnez une seule version.", messages.ERROR)
            return
        try:
            activate_envelope(actor=request.user, version_id=queryset.get().pk)
            self.message_user(request, "Version budgétaire activée ; les écritures existantes sont conservées.")
        except ValidationError as error:
            self.message_user(request, " · ".join(error.messages), messages.ERROR)

    @admin.action(description="Copier en nouvelle version brouillon", permissions=["change"])
    @transaction.atomic
    def clone(self, request, queryset):
        for source in queryset:
            target = EnvelopeVersion.objects.create(envelope=source.envelope, label=source.label + " (copie)")
            for allocation in source.allocations.all():
                allocation.pk = None
                allocation.version = target
                allocation.save()
        self.message_user(request, "Versions copiées en brouillon.")


class FinancialReadOnlyAdmin(ReadOnlyAdmin):
    def has_view_permission(self, request, obj=None):
        if self.model._meta.app_label == "budgeting":
            return request.user.has_perm("budgeting.view_budget_balances") and super().has_view_permission(request, obj)
        return request.user.has_perm("purchasing.view_purchase_financial") and super().has_view_permission(request, obj)


@admin.register(PurchaseOrder)
class OrderAdmin(FinancialReadOnlyAdmin):
    list_display = ("number", "purchase_request", "created_at")


for model in (Submission, LineSnapshot, BudgetEntry, ApprovalStep):
    admin.site.register(model, FinancialReadOnlyAdmin)

for model in (Allocation,):
    admin.site.register(model, FinancialReadOnlyAdmin)

admin.site.register(Delegation, ReadOnlyAdmin)
admin.site.register(PurchaseNotice, ReadOnlyAdmin)

admin.site.site_header = "BF ERP · Administration"
admin.site.site_title = "BF ERP"
admin.site.index_title = "Référentiels et configuration des achats"
