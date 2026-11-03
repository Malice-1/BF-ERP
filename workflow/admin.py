from django.contrib import admin

from .models import ActivityLog
from .models import AuditEvent, ConfigurationAuditEvent
from accounts.admin import ReadOnlyAdmin

admin.site.register(AuditEvent, ReadOnlyAdmin)
admin.site.register(ConfigurationAuditEvent, ReadOnlyAdmin)


class ActorFilter(admin.SimpleListFilter):
    title = "utilisateur (y compris supprimé)"
    parameter_name = "actor"

    def lookups(self, request, model_admin):
        rows = ActivityLog.objects.order_by("actor_username", "actor_identifier").values_list(
            "actor_identifier", "actor_username").distinct()
        return [(identifier, f"{username} — identifiant {identifier}") for identifier, username in rows]

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(actor_identifier=self.value())
        return queryset


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor_username", "actor_identifier", "action", "object_type", "object_identifier")
    list_filter = (ActorFilter, "action", "object_type")
    search_fields = ("actor_username", "actor_identifier", "action", "object_identifier")
    date_hierarchy = "created_at"
    readonly_fields = tuple(field.name for field in ActivityLog._meta.fields)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
