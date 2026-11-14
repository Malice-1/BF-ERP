from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from . import test_stock
from .services import move
from .models import StockMovement


@skipUnless(connection.vendor == "postgresql", "Nécessite les verrous PostgreSQL")
class ConcurrentStockTests(TransactionTestCase):
    setUp = test_stock.StockTests.setUp
    quantity = test_stock.StockTests.quantity

    def test_concurrent_issues_cannot_overdraw_stock(self):
        move(actor=self.actor, warehouse=self.source, product=self.product, kind="receipt",
             quantity=Decimal(10), reason="Entrée", token=uuid4())
        barrier = Barrier(2)
        def issue(_):
            close_old_connections()
            try:
                actor = get_user_model().objects.get(pk=self.actor.pk)
                barrier.wait(timeout=10)
                move(actor=actor, warehouse=self.source, product=self.product, kind="issue",
                     quantity=Decimal(6), reason="Sortie", token=uuid4())
                return "ok"
            except ValidationError:
                return "blocked"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertCountEqual(list(executor.map(issue, range(2))), ["ok", "blocked"])
        self.assertEqual(self.quantity(self.source), 4)
        self.assertEqual(StockMovement.objects.count(), 2)
