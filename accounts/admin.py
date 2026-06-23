from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Role


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

