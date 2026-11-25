from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from workflow.models import ActivityLog
from .fixed_assets import depreciation, schedule
from .models import FixedAsset


class FixedAssetTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("inventory")
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.start = self.today - timedelta(days=30)
        self.fields = dict(code="INV-1", label="Poste de travail", category="Informatique",
            acquired_on=self.start, in_service_on=self.start, cost="1200.00",
            residual_value="100.00", useful_life_months=36, revision=0)

    def grant(self, *codenames):
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="accounting", codename__in=codenames))

    def test_depreciation_rounds_cumulatively_and_stops_at_disposal(self):
        asset = FixedAsset(in_service_on=date(2024, 2, 29), cost=Decimal("1000.00"),
            residual_value=Decimal("100.00"), useful_life_months=12)
        rows = list(schedule(asset))
        self.assertEqual(sum(row[1] for row in rows), 365)
        self.assertEqual(sum(row[2] for row in rows), Decimal("900.00"))
        self.assertEqual(rows[-1][-1], Decimal("100.00"))
        asset.disposed_on = date(2024, 5, 29)
        self.assertEqual(depreciation(asset, date(2026, 1, 1)), Decimal("221.92"))
        self.assertEqual(list(schedule(asset))[-1][-1], Decimal("778.08"))

    def test_lifecycle_rejects_stale_changes_and_protects_financial_values(self):
        self.grant("view_fixedasset", "add_fixedasset", "change_fixedasset")
        create = reverse("accounting:asset_new")
        self.assertContains(self.client.get(create), 'name="revision"')
        response = self.client.post(create, self.fields)
        self.assertEqual(response.status_code, 302, response.context)
        asset = FixedAsset.objects.get(code="INV-1")
        edit = reverse("accounting:asset_edit", args=[asset.pk])
        response = self.client.post(edit, {**self.fields, "cost": "1800.00"})
        self.assertContains(response, "La fiche a été modifiée")
        activate = reverse("accounting:asset_activate", args=[asset.pk])
        self.assertEqual(self.client.post(activate, {"revision": asset.revision}).status_code, 302)
        asset.refresh_from_db()
        response = self.client.post(edit, {"revision": asset.revision, "location": "Atelier", "cost": "50.00"})
        self.assertEqual(response.status_code, 302)
        asset.refresh_from_db()
        self.assertEqual((asset.location, asset.cost), ("Atelier", Decimal("1200.00")))
        dispose = reverse("accounting:asset_dispose", args=[asset.pk])
        response = self.client.post(dispose, dict(revision=asset.revision, disposed_on=self.today,
            disposal_reason="Remplacement", proceeds="200.00"), follow=True)
        self.assertContains(response, "Valeur nette calculée à la sortie")
        asset.refresh_from_db()
        self.assertEqual(asset.status, FixedAsset.Status.DISPOSED)
        self.assertEqual(self.client.get(edit).status_code, 404)
        self.assertEqual(ActivityLog.objects.filter(object_type="accounting.fixedasset").count(), 4)
        self.assertEqual(self.client.get(reverse("accounting:assets"), {
            "status": "DISPOSED", "export": "xlsx"}).status_code, 200)

    def test_permissions_and_invalid_values(self):
        index = reverse("accounting:assets")
        create = reverse("accounting:asset_new")
        self.assertEqual(self.client.get(index).status_code, 403)
        self.grant("view_fixedasset")
        self.assertContains(self.client.get(index), "Immobilisations")
        self.assertEqual(self.client.post(create, self.fields).status_code, 403)
        self.grant("add_fixedasset")
        response = self.client.post(create, {**self.fields, "residual_value": "2000.00"})
        self.assertContains(response, "ne peut pas dépasser")
        self.assertFalse(FixedAsset.objects.exists())
