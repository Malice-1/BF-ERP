from datetime import timedelta
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import SessionPolicy
from workflow.models import ConfigurationAuditEvent


class IdleSessionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("idle", password="test")
        self.client.force_login(self.user)

    def activity(self, seconds_ago):
        session = self.client.session
        session["last_activity_at"] = timezone.now().timestamp() - seconds_ago
        session.save()

    def test_default_expiry_blocks_post_before_view(self):
        self.activity(7201)
        response = self.client.post(reverse("purchasing:create"), {})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_activity_slides_timeout_but_poll_does_not(self):
        self.activity(7100)
        previous = self.client.session["last_activity_at"]
        response = self.client.get(reverse("session_status"))
        self.assertTrue(response.json()["authenticated"])
        self.assertEqual(self.client.session["last_activity_at"], previous)
        self.client.get(reverse("purchasing:list"))
        self.assertGreater(self.client.session["last_activity_at"], previous)

    def test_new_policy_applies_to_existing_sessions(self):
        self.activity(61)
        SessionPolicy.objects.create(pk=1, idle_timeout_minutes=1)
        self.assertFalse(self.client.get(reverse("session_status")).json()["authenticated"])

    def test_old_session_without_timestamp_expires(self):
        Session.objects.filter(session_key=self.client.session.session_key).update(
            expire_date=timezone.now() + timedelta(seconds=1209600 - 7300))
        self.assertFalse(self.client.get(reverse("session_status")).json()["authenticated"])

    def test_login_initializes_activity(self):
        self.client.logout()
        self.client.post(reverse("login"), {"username": "idle", "password": "test"})
        self.assertIn("last_activity_at", self.client.session)

    def test_second_login_replaces_first_session_only(self):
        other_browser = Client()
        login = reverse("login")
        status = reverse("session_status")
        self.assertTrue(self.client.get(status).json()["authenticated"])

        other_browser.post(login, {"username": "idle", "password": "wrong"})
        self.assertTrue(self.client.get(status).json()["authenticated"])

        response = other_browser.post(login, {"username": "idle", "password": "test"})
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("purchasing:create"), {})
        self.assertEqual(response.status_code, 302)
        self.assertIn(login, response.url)
        self.assertFalse(self.client.get(status).json()["authenticated"])
        self.assertTrue(other_browser.get(status).json()["authenticated"])

    def test_policy_superuser_only_validated_and_audited(self):
        url = reverse("session_settings")
        self.assertEqual(self.client.post(url, {"idle_timeout_minutes": 1}).status_code, 403)
        self.user.is_staff = True
        self.user.save()
        self.assertEqual(self.client.get(url).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        for value in (0, -1, 10081, "bad"):
            response = self.client.post(url, {"idle_timeout_minutes": value})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(SessionPolicy.objects.exists())
        self.assertEqual(self.client.post(url, {"idle_timeout_minutes": 30}).status_code, 302)
        self.assertEqual(SessionPolicy.timeout_seconds(), 1800)
        self.assertEqual(ConfigurationAuditEvent.objects.get().payload, {"idle_timeout_minutes": 30})

    def test_expiry_also_protects_admin(self):
        self.user.is_staff = self.user.is_superuser = True
        self.user.save()
        self.activity(7201)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
