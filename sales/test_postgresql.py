from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from decimal import Decimal
from datetime import date
from uuid import uuid4
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, connections, transaction, DatabaseError
from django.test import TransactionTestCase

from .tests import SalesFixture
from . import services
from .models import SalesInvoice, SalesOrder, SalesInvoiceLine, InvoicePayment


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL locks and history guards")
class SalesPostgreSQLTests(SalesFixture, TransactionTestCase):
    def test_simultaneous_first_order_numbers_are_unique(self):
        barrier = Barrier(2)
        actor_id = self.actor.pk

        def create():
            connections.close_all()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=15)
                return services.save_order(actor=actor, values=self.values(), lines=[self.line()]).number
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            numbers = list(executor.map(lambda _: create(), range(2)))
        self.assertEqual(set(numbers), {"CV-2026-0001", "CV-2026-0002"})

    def test_two_simultaneous_requests_issue_one_invoice(self):
        order = self.confirm(self.order())
        barrier = Barrier(2)
        actor_id = self.actor.pk

        def issue():
            connections.close_all()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=15)
                try:
                    invoice = services.issue_invoice(actor=actor, pk=order.pk, revision=order.revision)
                    return ("issued", invoice.number)
                except ValidationError:
                    return ("rejected", None)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: issue(), range(2)))
        self.assertEqual([r[0] for r in results].count("issued"), 1, results)
        self.assertEqual([r[0] for r in results].count("rejected"), 1, results)
        self.assertEqual(SalesInvoice.objects.filter(order=order).count(), 1)
        self.assertEqual(SalesInvoice.objects.get(order=order).documents.count(), 1)

    def test_issued_data_cannot_be_changed_by_bulk_sql(self):
        invoice = self.invoice()
        for operation in (
            lambda: SalesInvoice.objects.filter(pk=invoice.pk).update(total=1),
            lambda: SalesInvoice.objects.filter(pk=invoice.pk).delete(),
            lambda: SalesInvoiceLine.objects.filter(invoice=invoice).update(description="Altered"),
            lambda: SalesInvoiceLine.objects.filter(invoice=invoice).delete(),
            lambda: SalesOrder.objects.filter(pk=invoice.order_id).update(customer_reference="Altered"),
            lambda: invoice.order.lines.all().update(unit_price=1),
            lambda: invoice.documents.all().update(checksum="0" * 64),
            lambda: invoice.events.all().delete(),
        ):
            with self.subTest(operation=operation), self.assertRaises((DatabaseError, ValidationError)):
                with transaction.atomic():
                    operation()

    def test_raw_sql_is_guarded_independently_from_orm(self):
        invoice = self.invoice()
        for sql in (
            "UPDATE sales_salesinvoice SET total=1 WHERE id=%s",
            "UPDATE sales_salesinvoiceline SET quantity=1 WHERE invoice_id=%s",
            "DELETE FROM sales_invoicedocument WHERE invoice_id=%s",
        ):
            with self.subTest(sql=sql), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(sql, [invoice.pk])

    def test_unique_invoice_constraint(self):
        invoice = self.invoice()
        from django.db import IntegrityError
        invoice.pk = None
        invoice.number = "FV-2026-9999"
        invoice._state.adding = True
        with self.assertRaises(IntegrityError), transaction.atomic():
            invoice.save(force_insert=True)

    def test_simultaneous_payments_cannot_overpay(self):
        invoice = self.invoice()
        barrier = Barrier(2)
        actor_id = self.actor.pk

        def pay():
            connections.close_all()
            try:
                actor = get_user_model().objects.get(pk=actor_id)
                barrier.wait(timeout=15)
                try:
                    services.record_payment(actor=actor, pk=invoice.pk, amount=Decimal("400"),
                        payment_date=date(2026, 11, 16), reference="Concurrent", token=uuid4())
                    return "paid"
                except ValidationError:
                    return "rejected"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: pay(), range(2)))
        self.assertEqual(sorted(results), ["paid", "rejected"])
        self.assertEqual(services.paid_amount(invoice), Decimal("400"))
