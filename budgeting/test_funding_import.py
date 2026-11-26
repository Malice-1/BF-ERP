from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .models import Funding


class FundingImportTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin"))
        self.list_url = reverse("admin:budgeting_funding_changelist")
        self.import_url = reverse("admin:budgeting_funding_import_excel")
        self.export_url = reverse("admin:budgeting_funding_export_excel")

    def upload(self, *rows):
        template = self.client.get(self.import_url, {"patron": "1"})
        self.assertEqual(template.status_code, 200)
        workbook = load_workbook(BytesIO(template.content))
        with BytesIO() as content:
            for row in rows:
                workbook.active.append(row)
            workbook.save(content)
            workbook.close()
            return self.client.post(self.import_url, {"file": SimpleUploadedFile("financements.xlsx", content.getvalue())})

    def test_import_template_and_filtered_export(self):
        self.assertContains(self.client.get(self.list_url), "Télécharger le patron Excel")
        self.assertRedirects(self.upload(("001", "Subsides", "Inactif"), ("002", "Dotation", None)), self.list_url)
        self.assertTrue(Funding.objects.get(code="002").is_active)
        filters = {"is_active__exact": "0"}
        self.assertContains(self.client.get(self.list_url, filters), f'{self.export_url}?is_active__exact=0')
        download = self.client.get(self.export_url, filters)
        self.assertEqual(download.status_code, 200)
        workbook = load_workbook(BytesIO(download.content))
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook.active.values), [
            ("Code", "Libellé", "Statut"), ("001", "Subsides", "Inactif"),
        ])

    def test_duplicate_code_rejects_entire_import(self):
        Funding.objects.create(code="001", label="Subsides")
        response = self.upload(("002", "Dotation", "Actif"), ("001", "Autre", "Inactif"))
        self.assertContains(response, "Le financement 001 existe déjà.")
        self.assertEqual(list(Funding.objects.values_list("code", "label", "is_active")), [("001", "Subsides", True)])
