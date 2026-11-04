from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from .rules import matches, validate, register_operation, OPERATIONS, Field


class PredicateTests(SimpleTestCase):
    def test_nested_and_or_and_decimal_boundaries(self):
        predicate = {"all": [
            {"field": "line.tvac", "op": "gte", "value": "100,01"},
            {"any": [{"field": "line.cdf", "op": "eq", "value": "3"},
                     {"field": "request.support", "op": "eq", "value": "4"}]},
        ]}
        facts = {"line.tvac": Decimal("100.01"), "line.cdf": 3, "request.support": None}
        self.assertTrue(matches("purchase", predicate, facts))
        self.assertFalse(matches("purchase", predicate, {**facts, "line.tvac": Decimal("100.0099999999")}))
        self.assertFalse(matches("purchase", {"field": "request.support", "op": "ne", "value": "4"}, facts))

    def test_rejects_unknown_fields_operators_values_and_executable_expressions(self):
        for expression in ({"field": "__import__('os')", "op": "eq", "value": 1},
                           {"field": "line.cdf", "op": "gt", "value": 1},
                           {"field": "line.tvac", "op": [], "value": 1},
                           {"field": "line.tvac", "op": "eq", "value": "NaN"},
                           {"field": "line.tvac", "op": "eq", "value": "Infinity"},
                           {"field": "line.tvac", "op": "eq", "value": -1},
                           {"any": []}, {"all": "not-a-list"}):
            with self.subTest(expression=expression), self.assertRaises(ValidationError):
                validate("purchase", expression)

    def test_another_operation_registers_its_own_fields_without_purchase_dependencies(self):
        register_operation("test-transfer", "Transfert de test", {"amount": Field("Montant transféré")})
        try:
            self.assertTrue(matches("test-transfer", {"field": "amount", "op": "gte", "value": "500"}, {"amount": Decimal("500")}))
            with self.assertRaises(ValidationError):
                validate("test-transfer", {"field": "line.tvac", "op": "eq", "value": 1})
        finally:
            OPERATIONS.pop("test-transfer")
