from io import BytesIO

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook, load_workbook

from .models import User


class UserImportTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin")
        self.client.force_login(self.admin)
        self.list_url = reverse("admin:accounts_user_changelist")
        self.import_url = reverse("admin:accounts_user_import_excel")
        self.export_url = reverse("admin:accounts_user_export_excel")

    def upload(self, *rows):
        response = self.client.get(self.import_url, {"patron": "1"})
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        return self.post_workbook(workbook, *rows)

    def post_workbook(self, workbook, *rows):
        with BytesIO() as output:
            for row in rows:
                workbook.active.append(row)
            workbook.save(output)
            workbook.close()
            return self.client.post(self.import_url, {"file": SimpleUploadedFile("utilisateurs.xlsx", output.getvalue())})

    def test_import_links_existing_and_new_managers_and_sets_password(self):
        self.assertContains(self.client.get(self.list_url), "Télécharger le patron Excel")
        self.assertRedirects(self.upload(
            ("alex", "Martin", "Alex", "alex@example.com", "sam"),
            ("sam", "Dupont", "Sam", "sam@example.com", "admin"),
        ), self.list_url)
        alex = User.objects.get(username="alex")
        self.assertEqual((alex.last_name, alex.first_name, alex.email), ("Martin", "Alex", "alex@example.com"))
        self.assertEqual(alex.manager.username, "sam")
        self.assertEqual(alex.manager.manager, self.admin)
        for user in (alex, alex.manager):
            self.assertTrue(user.check_password("User123!"))
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_staff or user.is_superuser)
            self.assertFalse(user.roles.exists())
        self.assertContains(self.client.get(reverse("admin:accounts_user_change", args=[alex.pk])), 'name="manager"')

    def test_unknown_manager_rejects_entire_file(self):
        response = self.upload(("alex", "Martin", "Alex", None, None), ("sam", None, None, None, "missing"))
        self.assertContains(response, "Ligne 3 — Aucun utilisateur avec l’identifiant missing.")
        self.assertEqual(list(User.objects.values_list("username", flat=True)), ["admin"])

    def test_import_accepts_inactive_status_and_rejects_invalid_values(self):
        response = self.upload(("alex", None, None, None, None, "Inconnu"))
        self.assertContains(response, "Ligne 2 — Le statut doit être Actif ou Inactif.")
        self.assertFalse(User.objects.filter(username="alex").exists())
        response = self.upload(("alex", None, None, None, None, " inactif "))
        self.assertRedirects(response, self.list_url)
        self.assertFalse(User.objects.get(username="alex").is_active)

    def test_original_template_defaults_to_active(self):
        workbook = Workbook()
        self.assertRedirects(self.post_workbook(
            workbook, ("Nom d’utilisateur", "Nom", "Prénom", "Mail", "Responsable"), ("alex",),
        ), self.list_url)
        self.assertTrue(User.objects.get(username="alex").is_active)

    def test_import_without_mail_column(self):
        self.assertRedirects(self.post_workbook(
            Workbook(), ("Nom d’utilisateur", "Nom", "Prénom", "Responsable", "Statut"),
            ("alex", "Martin", "Alex", "admin", "Inactif"),
        ), self.list_url)
        user = User.objects.get(username="alex")
        self.assertEqual(user.email, "")
        self.assertEqual(user.manager, self.admin)
        self.assertFalse(user.is_active)

    def test_import_without_optional_columns(self):
        self.assertRedirects(self.post_workbook(
            Workbook(), ("Nom d’utilisateur", "Nom", "Prénom"), ("alex", "Martin", "Alex"),
        ), self.list_url)
        user = User.objects.get(username="alex")
        self.assertIsNone(user.manager)
        self.assertEqual(user.email, "")
        self.assertTrue(user.is_active)

    def test_export_is_filtered_and_does_not_include_credentials(self):
        viewer = User.objects.create_user("viewer", is_staff=True)
        User.objects.create_user("alex", email="alex@example.com", manager=self.admin, is_active=False)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.export_url).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(codename="view_user"))
        self.assertEqual(self.client.get(self.import_url, {"patron": "1"}).status_code, 403)
        response = self.client.get(self.export_url, {"q": "alex"})
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook.active.values), [
            ("Nom d’utilisateur", "Nom", "Prénom", "Mail", "Responsable", "Statut"),
            ("alex", None, None, "alex@example.com", "admin", "Inactif"),
        ])
