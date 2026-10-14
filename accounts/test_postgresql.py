from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection, DatabaseError, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from .models import AuthorizationVersion, ValidationFunction
from .services import publish_authorization


@skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL immutable-history trigger")
class PostgreSQLAuthorizationTests(TransactionTestCase):
    def test_queryset_cannot_rewrite_version(self):
        actor = get_user_model().objects.create_user(username="administrator")
        actor.user_permissions.add(Permission.objects.get(codename="manage_authorizations"))
        function = ValidationFunction.objects.create(code="CDF", label="CDF", position=1)
        version = publish_authorization(actor=actor, user=actor, function=function, valid_from=timezone.now())
        with self.assertRaises(DatabaseError), transaction.atomic():
            AuthorizationVersion.objects.filter(pk=version.pk).update(enabled=False)
        version.refresh_from_db()
        self.assertTrue(version.enabled)
