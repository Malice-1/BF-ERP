from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from accounts.models import ValidationFunction, Authorization
from accounts.services import publish_authorization
from budgeting.models import CostCenter, Funding, BudgetProduct, DetailedProduct, CostCenterManagerAssignment
from budgeting.services import assign_cost_center_manager
from suppliers.models import Supplier
from purchasing.models import AnnualEnvelope, EnvelopeVersion, Allocation, WorkflowVersion, ApprovalRule, PurchaseRequest
from purchasing.services import create_purchase_request, add_purchase_request_line
from purchasing.flow import activate_envelope, activate_workflow


class Command(BaseCommand):
    help = "Crée un jeu de recette isolé ; uniquement avec config.demo_settings. Réexécutable sans réinitialiser les données."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="TestAchats!2026", help="Mot de passe initial des nouveaux comptes de démonstration.")

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.SETTINGS_MODULE != "config.demo_settings":
            raise CommandError("Utilisez --settings=config.demo_settings. Aucune donnée de démonstration n'est ajoutée à la base habituelle.")
        users = {}
        for name in ("admin", "demandeur", "cdf", "finance", "suivi", "budget"):
            user, created = get_user_model().objects.get_or_create(username="demo." + name,
                defaults={"is_staff": name == "admin", "is_superuser": name == "admin",
                          "email": f"{name}@example.test", "first_name": name.capitalize()})
            if created:
                user.set_password(options["password"])
                user.save()
            users[name] = user
        admin = users["admin"]
        from purchasing.budget_views import MANAGER_PERMISSIONS
        for name in (*MANAGER_PERMISSIONS, "budgeting.view_budget_balances", "budgeting.add_budgetproduct"):
            app_label, codename = name.split(".")
            users["budget"].user_permissions.add(Permission.objects.get(
                content_type__app_label=app_label, codename=codename))
        for name in ("cdf", "finance"):
            users[name].user_permissions.add(Permission.objects.get(content_type__app_label="purchasing", codename="view_purchase_financial"))
        users["suivi"].user_permissions.add(Permission.objects.get(content_type__app_label="purchasing", codename="monitor_purchases"))
        cdf, _ = CostCenter.objects.get_or_create(code="DEMO-CDF", defaults={"label": "Centre de formation de démonstration"})
        funding, _ = Funding.objects.get_or_create(code="DEMO-FONDS", defaults={"label": "Financement de démonstration"})
        product, _ = BudgetProduct.objects.get_or_create(code="DEMO-BUREAU", defaults={"label": "Fournitures de démonstration"})
        detailed, _ = DetailedProduct.objects.get_or_create(code="DEMO-PAPIER", defaults={"label": "Papier A4", "budget_product": product})
        supplier, _ = Supplier.objects.get_or_create(code="DEMO-FOURN", defaults={"name": "Fournisseur fictif — recette"})
        first, _ = ValidationFunction.objects.get_or_create(code="DEMO-CDF", defaults={"label": "Responsable CDF (démo)", "position": 100})
        second, _ = ValidationFunction.objects.get_or_create(code="DEMO-FINANCE", defaults={"label": "Finance (démo)", "position": 200})
        for name, function in (("cdf", first), ("finance", second)):
            if not Authorization.objects.filter(user=users[name], function=function).exists():
                publish_authorization(actor=admin, user=users[name], function=function,
                    valid_from=timezone.now() - timedelta(days=1), scope={})
        cdf.managers.add(users["cdf"])
        if not CostCenterManagerAssignment.objects.filter(cost_center=cdf).exists():
            assign_cost_center_manager(actor=admin, cost_center=cdf, user=users["cdf"], valid_from=timezone.now() - timedelta(days=1))
        envelope, _ = AnnualEnvelope.objects.get_or_create(year=timezone.localdate().year)
        if not envelope.active_version_id:
            version = EnvelopeVersion.objects.create(envelope=envelope, label="Budget de recette — 10 000 EUR TVAC")
            Allocation.objects.create(version=version, cost_center=cdf, funding=funding, budget_product=product, amount=Decimal("10000"))
            activate_envelope(actor=admin, version_id=version.pk)
        if not WorkflowVersion.objects.filter(active=True, operation="purchase").exists():
            workflow = WorkflowVersion.objects.create(label="Recette — CDF puis Finance")
            ApprovalRule.objects.create(version=workflow, label="Responsable CDF", function=first, level=1, cdf_manager=True)
            ApprovalRule.objects.create(version=workflow, label="Finance", function=second, level=2)
            activate_workflow(actor=admin, version_id=workflow.pk)
        if not PurchaseRequest.objects.filter(created_by=users["demandeur"]).exists():
            purchase = create_purchase_request(actor=users["demandeur"], supplier=supplier)
            for description, quantity, price in (("Ramettes A4", "10", "5"), ("Papier pour ateliers", "2", "25")):
                purchase.refresh_from_db()
                add_purchase_request_line(request_id=purchase.pk, actor=users["demandeur"], expected_revision=purchase.revision,
                    detailed_product=detailed, cost_center=cdf, funding=funding, description=description,
                    quantity=Decimal(quantity), unit_price=Decimal(price), vat_rate=Decimal("21"))
        self.stdout.write(self.style.SUCCESS("Jeu de recette prêt. Comptes : demo.demandeur, demo.cdf, demo.finance, demo.admin, demo.suivi, demo.budget."))
        self.stdout.write("Les nouveaux comptes utilisent --password (défaut documenté dans docs/RECETTE_ACHATS.md). Les mots de passe existants sont conservés.")
