from unittest.mock import patch
from purchasing.exceptions import PurchaseRequestError
from django.urls import reverse
from django.test import TestCase

from . import test_flow as fixtures
from .models import ApprovalStep


class SharedActionNavigationTests(TestCase):
    setUp = fixtures.PurchaseFlowTests.setUp
    grant = fixtures.PurchaseFlowTests.grant
    budget = fixtures.PurchaseFlowTests.budget
    draft = fixtures.PurchaseFlowTests.draft
    submit = fixtures.PurchaseFlowTests.submit

    def test_purchase_has_accessible_icons_and_actions_below_content(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertContains(response, 'aria-label="Ajouter une ligne"')
        self.assertContains(response, 'class="ui-icon ui-back"')
        self.assertNotContains(response, '&lt;svg')
        html = response.content.decode()
        self.assertGreater(html.index('aria-label="Actions de la demande"'), html.index('Parcours de validation'))

    def test_nonfinancial_reviewer_returns_to_its_inbox(self):
        self.submit()
        self.client.force_login(self.first)
        step = ApprovalStep.objects.get()
        response = self.client.get(reverse("purchasing:decision", args=[self.purchase.pk, step.pk]))
        self.assertContains(response, 'aria-label="Retour à mes validations"')
        self.assertNotContains(response, 'aria-label="Retour à la demande"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, 'aria-label="Confirmer"')

    def test_submit_returns_error_for_popup_without_changing_request(self):
        self.client.force_login(self.owner)
        self.purchase.refresh_from_db()
        revision = self.purchase.revision
        with patch("purchasing.flow_views.flow.submit_purchase", side_effect=PurchaseRequestError("Budget insuffisant : disponible 42000,00 EUR.")):
            response = self.client.post(reverse("purchasing:submit", args=[self.purchase.pk]),
                {"expected_revision": revision}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["errors"], ["Budget insuffisant : disponible 42000,00 EUR."])
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.revision, revision)
        detail = self.client.get(reverse("purchasing:detail", args=[self.purchase.pk]))
        self.assertContains(detail, 'id="purchase-error-dialog"')
        self.assertContains(detail, 'data-purchase-submit')

    def test_submit_returns_destination_after_success(self):
        self.client.force_login(self.owner)
        self.purchase.refresh_from_db()
        response = self.client.post(reverse("purchasing:submit", args=[self.purchase.pk]),
            {"expected_revision": self.purchase.revision}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["redirect"], reverse("purchasing:detail", args=[self.purchase.pk]))
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, "SUBMITTED")

    def test_order_can_be_loaded_for_direct_print_with_access_controls(self):
        purchase = self.submit()
        step = ApprovalStep.objects.get()
        fixtures.flow.decide(request_id=purchase.pk, actor=self.first, expected_revision=purchase.revision,
            step_id=step.pk, decision="approve")
        self.client.force_login(self.owner)
        url = reverse("purchasing:order", args=[purchase.pk])
        response = self.client.get(url)
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertContains(response, 'id="order-print-document"')
        self.assertContains(self.client.get(reverse("purchasing:detail", args=[purchase.pk])), 'data-print-order')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
