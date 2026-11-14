from datetime import date
from unittest.mock import patch

from django.test import TestCase

from suppliers.models import Supplier
from .models import PurchaseRequest, PurchaseRequestSequence


class PurchaseRequestNumberTests(TestCase):
    def setUp(self):
        self.supplier = Supplier.objects.create(code="NUMBER", name="Number supplier")

    def create(self):
        return PurchaseRequest.objects.create(supplier=self.supplier)

    def test_numbers_increment_and_restart_each_year(self):
        with patch("purchasing.models.timezone.localdate", return_value=date(2026, 12, 31)):
            first = self.create()
            second = self.create()
        with patch("purchasing.models.timezone.localdate", return_value=date(2027, 1, 1)):
            third = self.create()
        self.assertEqual(first.number, "DA-2026-0001")
        self.assertEqual(second.number, "DA-2026-0002")
        self.assertEqual(third.number, "DA-2027-0001")
        third.save()
        third.refresh_from_db()
        self.assertEqual(third.number, "DA-2027-0001")

    def test_numbers_are_not_reused_after_deletion(self):
        with patch("purchasing.models.timezone.localdate", return_value=date(2026, 1, 1)):
            self.create().delete()
            self.assertEqual(self.create().number, "DA-2026-0002")

    def test_unsaved_instance_does_not_consume_number(self):
        PurchaseRequest(supplier=self.supplier)
        self.assertFalse(PurchaseRequestSequence.objects.exists())

    def test_legacy_reference_is_preserved(self):
        legacy = PurchaseRequest.objects.create(supplier=self.supplier, number="DA-9D30A9A088B84D6FB3F1068FA1")
        legacy.status = PurchaseRequest.Status.CANCELLED
        legacy.save()
        legacy.refresh_from_db()
        self.assertEqual(legacy.number, "DA-9D30A9A088B84D6FB3F1068FA1")
