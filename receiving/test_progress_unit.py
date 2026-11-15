"""Receipt progress classification without database or stock writes."""
from decimal import Decimal

from django.test import SimpleTestCase

from .purchases import receipt_label


class ReceiptProgressUnitTests(SimpleTestCase):
    def test_no_receipt_is_distinct_from_completion(self):
        self.assertEqual(receipt_label(Decimal("10"), Decimal("0")), ("none", "Non réceptionnée"))

    def test_partial_receipt_is_identified(self):
        self.assertEqual(receipt_label(Decimal("10"), Decimal("4")), ("partial", "Partiellement réceptionnée"))

    def test_exact_receipt_is_complete(self):
        self.assertEqual(receipt_label(Decimal("10"), Decimal("10")), ("complete", "Réceptionnée"))

    def test_zero_order_does_not_appear_complete(self):
        self.assertEqual(receipt_label(Decimal("0"), Decimal("0")), ("none", "Non réceptionnée"))
