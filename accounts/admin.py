from accounts.admin_deletion import SystemModelAdmin, SystemDeletionMixin
from django.contrib import admin, messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.urls import path
from django.views.decorators.http import require_GET, require_http_methods

from config import excel

from .models import User, Role
from .models import Authorization, AuthorizationVersion
from .models import SessionPolicy
from .permission_labels import permission_label
from .user_import import HEADERS, INITIAL_PASSWORD, UserImportForm


class ReadOnlyAdmin(SystemModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser


admin.site.register(Authorization, ReadOnlyAdmin)
admin.site.register(AuthorizationVersion, ReadOnlyAdmin)
admin.site.register(SessionPolicy, ReadOnlyAdmin)


@admin.register(Role)
class RoleAdmin(SystemModelAdmin):
    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "permissions":
            field.label_from_instance = permission_label
        return field

    filter_horizontal = ("permissions",)
    list_display = ("code", "label")
    search_fields = ("code", "label")


@admin.register(User)
class CustomUserAdmin(SystemDeletionMixin, UserAdmin):
    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_superuser

    filter_horizontal = ("user_permissions", "roles", "supports")
    change_list_template = "admin/accounts/user/change_list.html"
    list_select_related = ("manager",)
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Responsable", {"fields": ("manager",)}),
        ("Rôles ERP et droits hérités", {"fields": ("roles",)}),
        ("Appartenance aux supports", {"fields": ("supports",)}),
    )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "user_permissions":
            field.label_from_instance = permission_label
        if db_field.name == "roles":
            field.label = "Rôles ERP"
            field.help_text = "Sélectionnez les rôles créés dans Configuration → Rôles ERP. Le compte hérite de leurs permissions."
        return field

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        field = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "manager":
            field.widget.can_add_related = False
            field.widget.can_change_related = False
            field.widget.can_delete_related = False
            field.widget.can_view_related = False
        return field

    fieldsets = UserAdmin.fieldsets[:2] + (
        ("Responsable", {"fields": ("manager",)}),
    ) + tuple(
        (title, {**options, "fields": tuple(field for field in options["fields"] if field != "groups")})
        for title, options in UserAdmin.fieldsets[2:]
    ) + (
        ("Appartenance aux supports", {"fields": ("supports",)}),
        (
            "Rôles ERP et droits hérités",
            {
                "fields": (
                    "roles",
                )
            },
        ),
    )

    list_display = (
        "username",
        "first_name",
        "last_name",
        "email",
        "manager",
        "is_active",
    )

    def get_urls(self):
        return [
            path("import-excel/", self.admin_site.admin_view(require_http_methods(["GET", "POST"])(self.import_excel)),
                 name="accounts_user_import_excel"),
            path("export-excel/", self.admin_site.admin_view(require_GET(self.export_excel)),
                 name="accounts_user_export_excel"),
        ] + super().get_urls()

    def import_excel(self, request):
        if not self.has_add_permission(request):
            raise PermissionDenied
        if request.method == "GET" and request.GET.get("patron") == "1":
            return excel.response("patron-utilisateurs", [("Utilisateurs", HEADERS, ())])
        form = UserImportForm(request.POST, request.FILES) if request.method == "POST" else UserImportForm()
        if request.method == "POST" and form.is_valid():
            users, by_username = form.cleaned_data["file"]
            try:
                with transaction.atomic():
                    for user, _ in users:
                        user.set_password(INITIAL_PASSWORD)
                        user.save(force_insert=True)
                        by_username[user.username] = user
                    for user, manager in users:
                        if manager:
                            user.manager = by_username[manager]
                            user.save(update_fields=["manager"])
                        self.log_addition(request, user, "Import Excel")
            except IntegrityError:
                form.add_error("file", "Impossible de terminer l’import. Vérifiez les identifiants et les responsables, puis réessayez.")
            else:
                self.message_user(request, f"Utilisateurs créés : {len(users)}.", messages.SUCCESS)
                return redirect(f"{self.admin_site.name}:accounts_user_changelist")
        return render(request, "admin/accounts/user/import_excel.html", {
            **self.admin_site.each_context(request),
            "title": "Importer des utilisateurs depuis Excel",
            "form": form,
        })

    def export_excel(self, request):
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied
        try:
            users = self.get_changelist_instance(request).queryset
        except IncorrectLookupParameters:
            return HttpResponseBadRequest("Les filtres de la liste des utilisateurs sont invalides.")
        rows = (
            (user.username, user.last_name, user.first_name, user.email,
             user.manager.username if user.manager else "", "Actif" if user.is_active else "Inactif")
            for user in users.iterator(chunk_size=500)
        )
        return excel.response("utilisateurs", [("Utilisateurs", HEADERS, rows)])


if admin.site.is_registered(Group):
    admin.site.unregister(Group)

