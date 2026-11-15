"""Pure unit checks complementing the integration and acceptance catalogue."""
from decimal import Decimal

from django.test import SimpleTestCase

from .allocation_excel import _code, _header
from .templatetags.ui_actions import amount


class ImportNormalizationUnitTests(SimpleTestCase):
    def test_header_normalizes_accents_spacing_and_case(self):
        self.assertEqual(_header("  Montánt   TVAC "), "MONTANT TVAC")

    def test_header_handles_missing_value(self):
        self.assertEqual(_header(None), "")

    def test_code_preserves_leading_zeroes_in_text(self):
        self.assertEqual(_code(" 0012 "), "0012")

    def test_code_rejects_boolean_as_reference(self):
        self.assertEqual(_code(True), "")
        self.assertEqual(_code(False), "")

    def test_numeric_code_converts_integral_float_without_suffix(self):
        self.assertEqual(_code(12.0), "12")


class AmountDisplayUnitTests(SimpleTestCase):
    def test_grouping_and_decimal_separator(self):
        self.assertEqual(amount(Decimal("1234567.89")), "1.234.567,89")

    def test_rounds_display_without_changing_decimal_value(self):
        value = Decimal("1200.125")
        self.assertEqual(amount(value), "1.200,13")
        self.assertEqual(value, Decimal("1200.125"))

    def test_negative_value_is_formatted(self):
        self.assertEqual(amount(Decimal("-42.125")), "-42,13")

    def test_zero_is_not_lost(self):
        self.assertEqual(amount(Decimal("0")), "0")
