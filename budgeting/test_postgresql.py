"""Run against configured PostgreSQL with manage.py test budgeting.test_postgresql."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from .models import CostCenter, CostCenterManagerAssignment
from .services import assign_cost_center_manager


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

    def test_concurrent_assignment_has_one_winner(self):
        barrier = Barrier(2)

        def assign():
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                barrier.wait(timeout=10)
                try:
                    assign_cost_center_manager(actor=actor, cost_center=self.cdf,
                        user=self.user, valid_from=self.now)
                    return "created"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: assign(), range(2)))
        self.assertCountEqual(results, ["created", "rejected"])
        self.assertEqual(CostCenterManagerAssignment.objects.count(), 1)
