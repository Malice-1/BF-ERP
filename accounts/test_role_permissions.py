from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, Group
from django.test import TestCase
from django.urls import reverse
from .models import Role


class RolePermissionTests(TestCase):
    def test_role_grant_and_revocation_on_protected_page(self):
        user = get_user_model().objects.create_user("member")
        role = Role.objects.create(code="READ", label="Consultation")
        permission = Permission.objects.get(content_type__app_label="purchasing", codename="view_all_purchase_requests")
        role.permissions.add(permission)
        self.client.force_login(user)
        url = reverse("purchasing:all_requests")
        self.assertEqual(self.client.get(url).status_code, 403)
        user.roles.add(role)
        self.assertEqual(self.client.get(url).status_code, 200)
        role.permissions.remove(permission)
        self.assertEqual(self.client.get(url).status_code, 403)
        role.permissions.add(permission)
        self.assertEqual(self.client.get(url).status_code, 200)
        user.roles.remove(role)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_permissions_combine_with_standard_grants_and_inactive_denied(self):
        user = get_user_model().objects.create_user("member")
        permissions = list(Permission.objects.filter(content_type__app_label="budgeting")[:3])
        role = Role.objects.create(code="R", label="Role")
        role.permissions.add(permissions[0])
        user.roles.add(role)
        group = Group.objects.create(name="Group")
        group.permissions.add(permissions[1])
        user.groups.add(group)
        user.user_permissions.add(permissions[2])
        user = get_user_model().objects.get(pk=user.pk)
        for permission in permissions:
            self.assertTrue(user.has_perm(f"budgeting.{permission.codename}"))
        user.is_active = False
        user.save()
        user = get_user_model().objects.get(pk=user.pk)
        self.assertFalse(user.has_perm(f"budgeting.{permissions[0].codename}"))
