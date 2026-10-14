from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.utils import timezone
from budgeting.models import CostCenter, Funding
from workflow.models import ConfigurationAuditEvent
from .models import AuthorizationVersion, ValidationFunction
from .services import eligible_authorization, publish_authorization


class AuthorizationTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username="admin")
        self.admin.user_permissions.add(Permission.objects.get(codename="manage_authorizations"))
        self.user = get_user_model().objects.create_user(username="validator")
        self.function = ValidationFunction.objects.create(code="CDF", label="Responsable CDF", position=1)
        self.cdf = CostCenter.objects.create(code="C", label="CDF")
        self.other = CostCenter.objects.create(code="D", label="Other")
        self.funding = Funding.objects.create(code="F", label="Funding")
        self.now = timezone.now()

    def publish(self, **overrides):
        data = dict(actor=self.admin, user=self.user, function=self.function,
                    valid_from=self.now, scope={})
        data.update(overrides)
        return publish_authorization(**data)

    def eligible(self, context, at=None):
        return eligible_authorization(user=self.user, function=self.function, context=context, at=at or self.now)

    def test_hab002_and_between_criteria_or_between_values(self):
        version = self.publish(scope={"cost_center": [self.cdf.pk, self.other.pk], "funding": [self.funding.pk]})
        self.assertEqual(self.eligible({"cost_center": self.other.pk, "funding": self.funding.pk}), version)
        self.assertIsNone(self.eligible({"cost_center": self.other.pk}))
        self.assertIsNone(self.eligible({"cost_center": 999, "funding": self.funding.pk}))

    def test_hab002_does_not_combine_partial_authorizations(self):
        self.publish(scope={"cost_center": [self.cdf.pk], "funding": [self.funding.pk]})
        self.publish(scope={"cost_center": [self.other.pk]})
        self.assertIsNone(self.eligible({"cost_center": self.cdf.pk, "funding": 999}))

    def test_hab001_date_bounds_and_inactive_user(self):
        end = self.now + timedelta(days=1)
        self.publish(valid_until=end)
        self.assertIsNotNone(self.eligible({}))
        self.assertIsNone(self.eligible({}, self.now - timedelta(seconds=1)))
        self.assertIsNone(self.eligible({}, end))
        self.user.is_active = False
        self.assertIsNone(self.eligible({}))

    def test_new_version_preserves_old_and_checks_revision(self):
        old = self.publish()
        new = self.publish(authorization_id=old.authorization_id, expected_version=1, enabled=False)
        old.refresh_from_db()
        self.assertTrue(old.enabled)
        self.assertEqual(new.version, 2)
        self.assertIsNone(self.eligible({}))
        with self.assertRaises(ValidationError):
            self.publish(authorization_id=old.authorization_id, expected_version=1)
        self.assertEqual(AuthorizationVersion.objects.count(), 2)
        self.assertEqual(ConfigurationAuditEvent.objects.count(), 2)
        with self.assertRaises(ValidationError):
            old.save()
        with self.assertRaises(ValidationError):
            old.delete()

    def test_permission_and_invalid_scope_leave_no_records(self):
        with self.assertRaises(PermissionDenied):
            self.publish(actor=self.user)
        for scope in ({"category": [1]}, {"cost_center": []}, {"funding": [999]}, {"cost_center": [True]}):
            with self.assertRaises(ValidationError):
                self.publish(scope=scope)
        self.assertEqual(AuthorizationVersion.objects.count(), 0)

    def test_deterministic_selection(self):
        first = self.publish()
        self.publish()
        self.assertEqual(self.eligible({}), first)

    def test_configuration_pages_are_permission_protected(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/habilitations/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/habilitations/").status_code, 200)
        self.assertEqual(self.client.get("/habilitations/nouvelle/").status_code, 200)
        version = self.publish()
        self.assertEqual(self.client.get(f"/habilitations/{version.authorization_id}/version/").status_code, 200)
