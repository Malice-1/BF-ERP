from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from suppliers.models import Supplier
from .test_supplier_xml import SupplierXmlFixture
from . import supplier_xml


class SupplierEnterpriseTests(SupplierXmlFixture, TestCase):
    def configure_number(self, value="BE0123.456.749", vat=""):
        self.supplier.enterprise_number = value
        self.supplier.vat_number = vat
        self.supplier.save()

    def test_company_id_finds_and_assigns_supplier_without_vat_on_its_form(self):
        self.configure_number()
        invoice = self.imported()
        self.assertEqual(invoice.supplier_id, self.supplier.pk)
        self.assertEqual(invoice.status, "RECEIVED")
        self.assertEqual([item.pk for item in supplier_xml.supplier_candidates(invoice)], [self.supplier.pk])
        approved = self.approved(invoice)
        self.assertEqual(approved.status, "REVIEWED")
        self.assertEqual(approved.review_snapshot["supplier_enterprise_number"], "0123456749")

    def test_existing_import_can_find_supplier_after_company_number_is_filled(self):
        invoice = self.imported()
        self.configure_number()
        response = self.client.get(reverse("accounting:supplier_invoice_detail", args=[invoice.pk]))
        self.assertEqual(response.context["review_form"].initial["supplier"], self.supplier.pk)
        self.assertEqual(self.approved(invoice).supplier_id, self.supplier.pk)

    def test_legacy_extraction_uses_original_without_rewriting_snapshot(self):
        invoice = self.imported()
        self.configure_number()
        invoice.extracted_data["seller"].pop("legal_id_scheme")
        invoice.extracted_data["seller"].pop("identifications")
        self.assertEqual([item.pk for item in supplier_xml.supplier_candidates(invoice)], [self.supplier.pk])
        self.assertNotIn("legal_id_scheme", invoice.extracted_data["seller"])

    def test_0208_endpoint_finds_supplier_when_company_id_is_absent(self):
        self.configure_number()
        data = self.data.replace(b"<cbc:CompanyID>0123456749</cbc:CompanyID>", b"")
        invoice = self.imported(data)
        self.assertEqual(invoice.supplier_id, self.supplier.pk)
        self.assertEqual(invoice.extracted_data["seller"]["legal_id"], "")

    def test_company_id_scheme_and_party_identification_are_extracted(self):
        self.configure_number()
        data = self.data.replace(b"<cbc:CompanyID>0123456749</cbc:CompanyID>",
            b'<cbc:CompanyID schemeID="0208">0123456749</cbc:CompanyID>')
        invoice = self.imported(data)
        self.assertEqual(invoice.extracted_data["seller"]["legal_id_scheme"], "0208")
        self.assertEqual(invoice.supplier_id, self.supplier.pk)
        _, extracted, _ = supplier_xml.parse(self.data)
        seller = extracted["seller"]
        seller.update(legal_id="", endpoint_id="", identifications=[{"id": "0123456749", "scheme": "0208"}])
        self.assertEqual(supplier_xml.seller_enterprise_numbers(seller), {"0123456749"})

    def test_duplicate_company_numbers_do_not_choose_a_supplier(self):
        self.configure_number()
        Supplier.objects.create(code="BRANCH", name="Autre fiche", enterprise_number="0123.456.749")
        invoice = self.imported()
        self.assertIsNone(invoice.supplier_id)
        self.assertEqual(len(supplier_xml.supplier_candidates(invoice)), 2)

    def test_different_company_number_is_not_bypassed_by_matching_vat(self):
        self.configure_number(value="0234567890", vat="BE0123456749")
        invoice = self.imported()
        self.assertEqual(supplier_xml.supplier_candidates(invoice), [])
        self.assertIsNone(invoice.supplier_id)
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_vat_conflict_blocks_approval_despite_matching_company_number(self):
        self.configure_number(vat="BE0000000097")
        invoice = self.imported()
        self.assertIsNone(invoice.supplier_id)
        with self.assertRaises(ValidationError):
            self.approved(invoice)

    def test_conflicting_xml_company_identifiers_are_not_automatically_matched(self):
        self.configure_number()
        data = self.data.replace(b"<cbc:CompanyID>0123456749</cbc:CompanyID>", b"<cbc:CompanyID>0234567890</cbc:CompanyID>")
        invoice = self.imported(data)
        self.assertIsNone(invoice.supplier_id)
        self.assertEqual(supplier_xml.supplier_candidates(invoice), [])
        with self.assertRaises(ValidationError):
            self.approved(invoice)
