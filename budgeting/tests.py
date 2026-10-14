from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from workflow.models import ConfigurationAuditEvent
from .models import CostCenter, CostCenterManagerAssignment
from .selectors import active_cost_center_manager
from .services import assign_cost_center_manager, end_cost_center_manager_assignment


class ManagerAssignmentTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="admin")
        self.admin.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.user = get_user_model().objects.create_user(username="manager")
        self.cdf = CostCenter.objects.create(code="C", label="CDF")
        self.now = timezone.now()

    def assign(self, **overrides):
        values = dict(actor=self.admin, cost_center=self.cdf, user=self.user, valid_from=self.now)
        values.update(overrides)
        return assign_cost_center_manager(**values)

    def test_org001_overlap_rejected_adjacent_allowed(self):
        end = self.now + timedelta(days=1)
        self.assign(valid_until=end)
        with self.assertRaises(ValidationError):
            self.assign(valid_from=self.now + timedelta(hours=1))
        following = self.assign(valid_from=end)
        self.assertEqual(active_cost_center_manager(self.cdf, at=end), following)
        self.assertEqual(CostCenterManagerAssignment.objects.count(), 2)
        self.assertEqual(ConfigurationAuditEvent.objects.count(), 2)

    def test_open_assignment_can_be_closed_and_replaced_with_gap(self):
        initial = self.assign()
        end = self.now + timedelta(days=1)
        end_cost_center_manager_assignment(actor=self.admin, assignment_id=initial.pk, valid_until=end)
        self.assertIsNone(active_cost_center_manager(self.cdf, at=end))
        self.assign(valid_from=end + timedelta(days=1))
        initial.refresh_from_db()
        self.assertEqual(initial.valid_until, end)
        self.assertEqual(ConfigurationAuditEvent.objects.count(), 3)

    def test_permission_inactive_and_invalid_dates(self):
        with self.assertRaises(PermissionDenied):
            self.assign(actor=self.user)
        with self.assertRaises(ValidationError):
            self.assign(valid_until=self.now)
        self.user.is_active = False
        with self.assertRaises(ValidationError):
            self.assign()
        self.assertEqual(CostCenterManagerAssignment.objects.count(), 0)

    def test_pages_expose_no_financial_information(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/responsables-cdf/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/responsables-cdf/").status_code, 200)
        self.assertEqual(self.client.get("/responsables-cdf/nouveau/").status_code, 200)
