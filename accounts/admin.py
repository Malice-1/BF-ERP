from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Role
from .models import ValidationFunction, Authorization, AuthorizationVersion


@admin.register(ValidationFunction)
class ValidationFunctionAdmin(admin.ModelAdmin):
    list_display = ("code", "label", "position")


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Authorization, ReadOnlyAdmin)
admin.site.register(AuthorizationVersion, ReadOnlyAdmin)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("code", "label")
    search_fields = ("code", "label")


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "ERP",
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

