from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase
from django.shortcuts import resolve_url
from django.urls import reverse


class LoginMessageTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "disabled", password="CorrectPassword!2026", is_active=False)

    def test_authenticated_user_is_redirected_away_from_login(self):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        self.client.force_login(self.user)
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, resolve_url(settings.LOGIN_REDIRECT_URL),
                             fetch_redirect_response=False)

    def test_anonymous_user_sees_login_without_authenticated_navigation(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Se connecter")
        self.assertNotContains(response, 'class="app-sidebar"')
        self.assertNotContains(response, 'class="header-username"')

    def test_disabled_account_with_correct_password_has_specific_message(self):
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "CorrectPassword!2026"})
        self.assertContains(response, "Ce compte est désactivé. Contactez votre administrateur.")
        self.assertEqual(response.context["form"].errors.as_data()["__all__"][0].code, "inactive")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.client.session["login_failures"], 1)
        self.assertIsNone(authenticate(username=self.user.username, password="CorrectPassword!2026"))

    def test_wrong_password_or_unknown_user_keeps_invalid_credentials_message(self):
        for username in (self.user.username, "unknown"):
            response = self.client.post(reverse("login"), {"username": username, "password": "wrong"})
            self.assertContains(response, "Identifiants de connexion incorrects.")
            self.assertNotContains(response, "Ce compte est désactivé.")
            self.assertNotIn("_auth_user_id", self.client.session)

    def test_reactivated_account_can_login(self):
        self.user.is_active = True
        self.user.save(update_fields=["is_active"])
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "CorrectPassword!2026"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))
