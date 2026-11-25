from datetime import date

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods

from .history_archive import MAX_ARCHIVE_BYTES, export_archive, purge_archive
from .models import BudgetHistoryEvent


class HistoryExportForm(forms.Form):
    before = forms.DateField(label="Événements antérieurs au", widget=forms.DateInput(
        format="%Y-%m-%d", attrs={"type": "date"}))
    year = forms.IntegerField(label="Exercice budgétaire", required=False, min_value=1, max_value=9999,
        help_text="Laisser vide pour inclure tous les exercices.")

    def clean_before(self):
        before = self.cleaned_data["before"]
        if before.year < 1900:
            raise ValidationError("Choisissez une date limite à partir de 1900.")
        return before


class HistoryPurgeForm(forms.Form):
    archive = forms.FileField(label="Fichier d’archive (.json.gz)", widget=forms.ClearableFileInput(
        attrs={"accept": ".gz,application/gzip"}))
    confirmed = forms.BooleanField(label="J’ai conservé le fichier et je confirme le retrait des événements archivés.")

    def clean_archive(self):
        archive = self.cleaned_data["archive"]
        if archive.size > MAX_ARCHIVE_BYTES:
            raise ValidationError("Le fichier dépasse la taille maximale de 32 Mio.")
        return archive


@admin.register(BudgetHistoryEvent)
class BudgetHistoryArchiveAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    def has_module_permission(self, request):
        return self.has_view_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @method_decorator(require_http_methods(["GET", "POST"]))
    def changelist_view(self, request, extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        post = request.POST if request.method == "POST" else None
        action = post.get("action") if post is not None else None
        export_form = HistoryExportForm(post if action == "export" else None,
            initial={"before": date(timezone.localdate().year, 1, 1)})
        purge_form = HistoryPurgeForm(post, request.FILES) if action == "purge" else HistoryPurgeForm()
        if action == "export" and export_form.is_valid():
            try:
                archive = export_archive(actor=request.user, **export_form.cleaned_data)
            except ValidationError as error:
                export_form.add_error(None, error)
            else:
                before = export_form.cleaned_data["before"]
                response = HttpResponse(archive, content_type="application/gzip")
                response["Content-Disposition"] = f'attachment; filename="historique-budgetaire-avant-{before}.json.gz"'
                return response
        if action == "purge" and purge_form.is_valid():
            try:
                count = purge_archive(actor=request.user, archive=purge_form.cleaned_data["archive"].read())
            except ValidationError as error:
                purge_form.add_error(None, error)
            else:
                messages.success(request, f"Purge effectuée. Événements supprimés : {count}.")
                return redirect(reverse("admin:budgeting_budgethistoryevent_changelist"))
        return render(request, "admin/budgeting/history_archive.html", {
            **self.admin_site.each_context(request), "opts": self.model._meta,
            "title": "Archivage de l’historique budgétaire",
            "export_form": export_form, "purge_form": purge_form,
        })
