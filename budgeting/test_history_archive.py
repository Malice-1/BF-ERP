from datetime import timedelta
import gzip
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from purchasing.models import AnnualEnvelope, EnvelopeVersion
from workflow.models import ActivityLog
from .models import BudgetHistoryEvent


class HistoryArchiveTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("archive-admin", password="test")
        self.client.force_login(self.admin)
        self.url = reverse("admin:budgeting_budgethistoryevent_changelist")
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.envelope = AnnualEnvelope.objects.create(year=self.today.year)
        self.version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Version principale")
        self.other_version = EnvelopeVersion.objects.create(envelope=self.envelope, label="Version parallèle")
        self.other = AnnualEnvelope.objects.create(year=self.today.year - 1)
        BudgetHistoryEvent.objects.update(created_at=self.now - timedelta(days=6))
        self.early = self.event(4, 10)
        self.anchor = self.event(3, 20, self.other_version.pk)
        self.recent = self.event(0, 40)
        self.other_event = self.event(4, 100, envelope=self.other)

    def event(self, days_ago, allocated, version_id=None, envelope=None):
        row = {"product": "BI", "cdf": "Centre", "funding": "Fonds", "allocated": str(allocated),
            "reserved": "0", "committed": "0", "transfers": "0", "available": str(allocated)}
        return BudgetHistoryEvent.objects.create(envelope=envelope or self.envelope,
            created_at=self.now - timedelta(days=days_ago), version_id=version_id, actor="test",
            reason="État de test", state={"versions": {
                str(self.version.pk): {"label": self.version.label, "status": "Active", "rows": [row]},
            }})

    def export(self):
        response = self.client.post(self.url, {
            "action": "export", "before": self.today.isoformat(), "year": self.envelope.year,
        })
        self.assertEqual(response["Content-Type"], "application/gzip")
        return response.content

    def purge(self, data, confirmed=True):
        return self.client.post(self.url, {"action": "purge", "confirmed": confirmed,
            "archive": SimpleUploadedFile("archive.json.gz", data, content_type="application/gzip")})

    def test_export_then_purge_keeps_anchor_for_history_and_recent_movements(self):
        self.assertContains(self.client.get(reverse("admin:index")), "Archivage de l’historique budgétaire")
        archive = self.export()
        payload = json.loads(gzip.decompress(archive))
        self.assertEqual([row["id"] for row in payload["events"]][-2:], [self.early.pk, self.anchor.pk])
        self.assertTrue(all(row["envelope_id"] == self.envelope.pk for row in payload["events"]))
        self.assertEqual(payload["retained_ids"], [self.anchor.pk])
        self.assertTrue(BudgetHistoryEvent.objects.filter(pk=self.early.pk).exists())
        self.assertContains(self.purge(archive, confirmed=""), "Ce champ est obligatoire.")
        self.assertContains(self.purge(archive + b"changed"), "aucune archive exportée")
        self.assertRedirects(self.purge(archive), self.url)
        self.assertFalse(BudgetHistoryEvent.objects.filter(pk=self.early.pk).exists())
        self.assertEqual(BudgetHistoryEvent.objects.filter(
            pk__in=(self.anchor.pk, self.recent.pk, self.other_event.pk)).count(), 3)
        self.assertContains(self.purge(archive), "déjà été utilisée")

        response = self.client.get(reverse("purchasing:budget_history"), {
            "version": self.version.pk, "at": self.anchor.created_at.isoformat(),
        })
        self.assertEqual(response.context["selected"].pk, self.anchor.pk)
        response = self.client.get(reverse("purchasing:budget_transactions"), {"version": self.version.pk})
        self.assertEqual([row["amount"] for row in response.context["page"]], [20])
        log = ActivityLog.objects.get(source__startswith="budget-history-purge:")
        self.assertEqual(log.details["removed"], len(payload["events"]) - 1)
        self.assertFalse(ActivityLog.objects.filter(object_type="budgeting.budgethistoryevent", action="deleted").exists())
        creation = ActivityLog.objects.get(object_type="budgeting.budgethistoryevent",
            object_identifier=str(self.early.pk), action="created")
        self.assertNotIn("state", creation.details["after"])

    def test_stale_export_and_staff_access_are_refused(self):
        archive = self.export()
        self.event(5, 5)
        self.assertContains(self.purge(archive), "L’historique a changé depuis l’export")
        self.assertTrue(BudgetHistoryEvent.objects.filter(pk=self.early.pk).exists())
        staff = get_user_model().objects.create_user("archive-staff", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.purge(archive).status_code, 403)
