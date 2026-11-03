from accounts.admin_deletion import SystemModelAdmin, SystemDeletionMixin
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from .models import User, Role
from .models import ValidationFunction, Authorization, AuthorizationVersion
from .models import SessionPolicy
from .permission_labels import permission_label


@admin.register(ValidationFunction)
class ValidationFunctionAdmin(SystemModelAdmin):
    list_display = ("code", "label", "position")


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

    filter_horizontal = ("user_permissions", "roles")
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Rôles ERP et droits hérités", {"fields": ("roles",)}),
    )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        field = super().formfield_for_manytomany(db_field, request, **kwargs)
        if db_field.name == "user_permissions":
            field.label_from_instance = permission_label
        if db_field.name == "roles":
            field.label = "Rôles ERP"
            field.help_text = "Sélectionnez les rôles créés dans Configuration → Rôles ERP. Le compte hérite de leurs permissions."
        return field

    fieldsets = tuple(
        (title, {**options, "fields": tuple(field for field in options["fields"] if field != "groups")})
        for title, options in UserAdmin.fieldsets
    ) + (
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
        "is_active",
    )


if admin.site.is_registered(Group):
    admin.site.unregister(Group)

