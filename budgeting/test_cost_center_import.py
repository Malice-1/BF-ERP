from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from .models import CostCenter


class CostCenterImportTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser("admin"))
        self.url = reverse("admin:budgeting_costcenter_import_excel")
        self.list_url = reverse("admin:budgeting_costcenter_changelist")

    def upload(self, *rows):
        download = self.client.get(self.url, {"patron": "1"})
        self.assertEqual(download.status_code, 200)
        with BytesIO() as output:
            workbook = load_workbook(BytesIO(download.content))
            for row in rows:
                workbook.active.append(row)
            workbook.save(output)
            workbook.close()
            return self.client.post(self.url, {"file": SimpleUploadedFile("cdf.xlsx", output.getvalue())})

    def test_template_links_and_import_status(self):
        self.assertContains(self.client.get(self.list_url), "Télécharger le patron Excel")
        response = self.upload(("001", "Formation", "Inactif"), ("002", "Gestion", None))
        self.assertRedirects(response, self.list_url)
        self.assertEqual(dict(CostCenter.objects.values_list("code", "is_active")), {"001": False, "002": True})

    def test_import_assigns_the_user_by_login(self):
        manager = get_user_model().objects.create_user("c.martin")
        self.assertRedirects(self.upload(("001", "Formation", "Actif", "c.martin")), self.list_url)
        self.assertEqual(list(CostCenter.objects.get(code="001").managers.all()), [manager])

    def test_unknown_or_inactive_manager_rejects_entire_workbook(self):
        get_user_model().objects.create_user("inactive", is_active=False)
        response = self.upload(("001", "Sans responsable", None, None),
                               ("002", "Inconnu", None, "missing"),
                               ("003", "Inactif", None, "inactive"))
        self.assertContains(response, "Ligne 3 — Aucun utilisateur actif avec l’identifiant missing.")
        self.assertContains(response, "Ligne 4 — Aucun utilisateur actif avec l’identifiant inactive.")
        self.assertFalse(CostCenter.objects.exists())

    def test_assigning_managers_requires_the_management_permission(self):
        importer = get_user_model().objects.create_user("importer", is_staff=True)
        importer.user_permissions.add(Permission.objects.get(codename="add_costcenter"))
        self.client.force_login(importer)
        self.assertEqual(self.upload(("001", "Formation", None, "admin")).status_code, 403)
        self.assertFalse(CostCenter.objects.exists())

    def test_existing_code_rejects_entire_workbook(self):
        CostCenter.objects.create(code="001", label="Formation")
        response = self.upload(("002", "Gestion", "Actif"), ("001", "Autre", "Inactif"))
        self.assertContains(response, "Le CDF 001 existe déjà.")
        self.assertEqual(list(CostCenter.objects.values_list("code", "label", "is_active")), [("001", "Formation", True)])

    def test_admin_can_deactivate_and_filter_a_center(self):
        center = CostCenter.objects.create(code="001", label="Formation")
        edit_url = reverse("admin:budgeting_costcenter_change", args=[center.pk])
        self.assertRedirects(self.client.post(edit_url, {"code": "001", "label": "Formation"}), self.list_url)
        center.refresh_from_db()
        self.assertFalse(center.is_active)
        self.assertContains(self.client.get(self.list_url, {"is_active__exact": "0"}), "Formation")

    def test_import_requires_add_permission(self):
        viewer = get_user_model().objects.create_user("viewer", is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename="view_costcenter"))
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(self.list_url), "Télécharger le patron Excel")
        self.assertEqual(self.client.get(self.url, {"patron": "1"}).status_code, 403)
        self.assertEqual(self.client.post(self.url).status_code, 403)

    def test_export_respects_filters_and_view_permission(self):
        User = get_user_model()
        viewer = User.objects.create_user("viewer", is_staff=True)
        center = CostCenter.objects.create(code="001", label="Formation", is_active=False)
        center.managers.add(User.objects.create_user("c.martin"), User.objects.create_user("a.dupont"))
        CostCenter.objects.create(code="002", label="Gestion")
        url = reverse("admin:budgeting_costcenter_export_excel")
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(url).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename="view_costcenter"))
        filters = {"is_active__exact": "0"}
        self.assertContains(self.client.get(self.list_url, filters), f'{url}?is_active__exact=0')
        download = self.client.get(url, filters)
        self.assertEqual(download.status_code, 200)
        workbook = load_workbook(BytesIO(download.content))
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook.active.values), [
            ("Code", "Libellé", "Statut", "Responsables"),
            ("001", "Formation", "Inactif", "a.dupont, c.martin"),
        ])
