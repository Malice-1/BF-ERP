from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from workflow.models import ActivityLog
from .models import Employee, PayrollDetails


class EmployeeTests(TestCase):
    def login(self, name, *permissions):
        user = get_user_model().objects.create_user(name)
        user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="hr", codename__in=permissions))
        self.client.force_login(user)
        return user

    def test_employee_and_payroll_can_be_saved_with_separate_access(self):
        self.login("rh-editor", "view_employee", "add_employee", "change_employee",
                   "view_payrolldetails", "change_payrolldetails")
        self.assertRedirects(self.client.get(reverse("purchasing:list")), reverse("hr:employees"))
        response = self.client.post(reverse("hr:employee_new"), {
            "revision": 0, "number": "RH-001", "first_name": "Camille", "last_name": "Test",
            "department": "Formation", "start_date": "2026-11-01", "is_active": "on",
        })
        employee = Employee.objects.get(number="RH-001")
        detail = reverse("hr:employee_detail", args=[employee.pk])
        payroll = reverse("hr:payroll", args=[employee.pk])
        self.assertRedirects(response, detail)
        values = {"revision": 0, "gross_amount": "3290.50", "frequency": "MONTHLY",
                  "work_percentage": "80", "effective_date": "2026-11-01", "iban": "BE68 5390 0754 7034"}
        self.assertRedirects(self.client.post(payroll, values), payroll)
        self.assertContains(self.client.post(payroll, {**values, "gross_amount": "5000"}), "Cette fiche a changé")
        record = PayrollDetails.objects.get(employee=employee)
        self.assertEqual((record.gross_amount, record.iban), (Decimal("3290.50"), "BE68539007547034"))
        self.assertEqual(ActivityLog.objects.get(object_type="hr.payrolldetails").details, {})
        self.assertIn("no-store", self.client.get(payroll)["Cache-Control"])

        self.login("rh-directory", "view_employee")
        self.assertContains(self.client.get(reverse("hr:employees"), {"q": "Camille Formation"}), "Camille Test")
        self.assertNotContains(self.client.get(detail), payroll)
        self.assertEqual(self.client.get(payroll).status_code, 403)
        self.assertEqual(self.client.post(payroll, values).status_code, 403)

        self.login("rh-payroll-reader", "view_employee", "view_payrolldetails")
        self.assertContains(self.client.get(payroll), "BE68539007547034")
        self.assertEqual(self.client.post(payroll, values).status_code, 403)

    def test_invalid_iban_and_employee_dates_are_rejected(self):
        self.login("rh-validation", "view_employee", "add_employee", "view_payrolldetails", "change_payrolldetails")
        response = self.client.post(reverse("hr:employee_new"), {
            "revision": 0, "number": "RH-002", "first_name": "Sacha", "last_name": "Test",
            "start_date": "2026-11-16", "end_date": "2026-11-01",
        })
        self.assertContains(response, "La date de sortie doit suivre")
        self.assertFalse(Employee.objects.exists())
        employee = Employee.objects.create(number="RH-002", first_name="Sacha", last_name="Test")
        response = self.client.post(reverse("hr:payroll", args=[employee.pk]), {
            "revision": 0, "frequency": "HOURLY", "iban": "BE68539007547035",
        })
        self.assertContains(response, "La clé de contrôle de l’IBAN est invalide")
        self.assertFalse(PayrollDetails.objects.exists())

    def test_live_search_returns_only_filtered_employee_results(self):
        self.login("rh-search", "view_employee")
        Employee.objects.create(number="RH-10", first_name="Camille", last_name="Martin")
        Employee.objects.create(number="RH-11", first_name="Camille", last_name="Leroy", is_active=False)
        url = reverse("hr:employees")
        self.assertContains(self.client.get(url), "employee_search.js")
        response = self.client.get(url, {"q": "Camille", "status": "active"},
                                   HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertContains(response, "Camille Martin")
        self.assertContains(response, 'data-result-count="1"')
        self.assertNotContains(response, "Camille Leroy")
        self.assertNotContains(response, "employee-search")
