from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from . import test_transfers
from .transfers import act


@skipUnless(connection.vendor == "postgresql", "Nécessite les verrous PostgreSQL")
class ConcurrentTransferTests(TransactionTestCase):
    setUp = test_transfers.TransferTests.setUp
    create_transfer = test_transfers.TransferTests.create_transfer
    balance = test_transfers.TransferTests.balance

    def parallel(self, commands):
        barrier = Barrier(len(commands))
        def run(command):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                command()
                return "ok"
            except ValidationError:
                return "blocked"
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(commands)) as executor:
            return list(executor.map(run, commands))

    def test_concurrent_transfers_cannot_overdraw_source(self):
        other = self.create_transfer()
        def submit(pk):
            act(pk=pk, actor=get_user_model().objects.get(pk=self.owner.pk), revision=0, action="submit")
        self.assertCountEqual(self.parallel([lambda: submit(self.transfer.pk), lambda: submit(other.pk)]), ["ok", "blocked"])
        self.assertEqual(self.balance(self.source), 40)
