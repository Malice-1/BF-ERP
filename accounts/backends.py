from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import Permission


class RolePermissionBackend(ModelBackend):
    """Combine standard user/group permissions with ERP role permissions."""

    def get_group_permissions(self, user_obj, obj=None):
        standard = super().get_group_permissions(user_obj, obj)
        if not user_obj.is_active or user_obj.is_anonymous or obj is not None:
            return standard
        if not hasattr(user_obj, "_role_perm_cache"):
            permissions = Permission.objects.filter(role__user=user_obj).values_list(
                "content_type__app_label", "codename")
            user_obj._role_perm_cache = {f"{app}.{code}" for app, code in permissions}
        return standard | user_obj._role_perm_cache
