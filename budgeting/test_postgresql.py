"""Run against configured PostgreSQL with manage.py test budgeting.test_postgresql."""
from datetime import timedelta
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from .models import CostCenter, CostCenterManagerAssignment


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL locks and exclusion constraint")
class PostgreSQLManagerTests(TransactionTestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user(username="administrator")
        self.actor.user_permissions.add(Permission.objects.get(codename="manage_cost_center_managers"))
        self.user = get_user_model().objects.create_user(username="manager")
        self.cdf = CostCenter.objects.create(code="CDF", label="CDF")
        self.now = timezone.now()

    def test_database_rejects_overlap_even_without_service(self):
        CostCenterManagerAssignment.objects.create(cost_center=self.cdf, user=self.user, valid_from=self.now)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CostCenterManagerAssignment.objects.create(cost_center=self.cdf, user=self.user,
                valid_from=self.now + timedelta(days=1))
