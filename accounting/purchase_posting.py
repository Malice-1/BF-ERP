from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from . import services
from .models import AccountingPeriod, BudgetProductAccount, JournalEntry, PurchasePostingConfiguration


SOURCE_KIND = "PURCHASE_REQUEST"


@transaction.atomic
def configure(*, actor, settings=None, mapping=None):
    services.require(actor, "change_purchasepostingconfiguration")
    services.profile_lock()
    if settings is not None:
        config, _ = PurchasePostingConfiguration.objects.update_or_create(pk=1, defaults=settings)
        services.audit(actor, config, "Paramétrage des engagements d’achat",
                       enabled=config.enabled, journal=config.journal_id, offset_account=config.offset_account_id)
    if mapping is not None:
        assigned, _ = BudgetProductAccount.objects.update_or_create(
            product=mapping["product"], defaults={"account": mapping["account"]})
        services.audit(actor, assigned, "Imputation du produit budgétaire",
                       product=assigned.product_id, account=assigned.account_id)


def create_engagement_draft(order, actor):
    """Called inside the transaction that changes a DA from reserved to committed."""
    if not PurchasePostingConfiguration.objects.filter(pk=1, enabled=True).exists():
        return
    services.profile_lock()
    config = PurchasePostingConfiguration.objects.filter(pk=1, enabled=True).select_related(
        "journal", "offset_account").first()
    if config is None:
        return
    purchase = order.purchase_request
    origin = str(purchase.pk)
    existing = JournalEntry.objects.filter(source_kind=SOURCE_KIND, source_identifier=origin).first()
    if existing is not None:
        return existing

    amounts = defaultdict(Decimal)
    for snapshot in order.submission.lines.select_related("budget_product").order_by("pk"):
        amounts[snapshot.budget_product] += snapshot.amount
    amounts = {
        product: rounded
        for product, amount in amounts.items()
        if (rounded := amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    }
    if not amounts:
        return
    accounts = {
        mapping.product_id: mapping.account
        for mapping in BudgetProductAccount.objects.filter(product__in=amounts).select_related("account")
    }
    missing = [str(product) for product in amounts if product.pk not in accounts]
    if missing:
        raise ValidationError("Compte d’imputation manquant pour les produits budgétaires suivants : " + ", ".join(missing))

    date = timezone.localdate(order.created_at)
    period = AccountingPeriod.objects.filter(start_date__lte=date, end_date__gte=date,
        is_open=True, fiscal_year__is_open=True).first()
    if period is None:
        raise ValidationError("Aucune période comptable ouverte à la date du bon de commande.")

    lines = []
    for product, amount in amounts.items():
        account = accounts[product.pk]
        if account.pk == config.offset_account_id:
            raise ValidationError(f"Le compte de {product} doit être distinct du compte de contrepartie.")
        lines.append({"account": account, "description": str(product)[:255], "debit": amount,
                      "supplier": purchase.supplier if account.party_requirement == "SUPPLIER" else None})
    offset = config.offset_account
    lines.append({"account": offset, "description": "Contrepartie de l’engagement",
                  "credit": sum(amounts.values()), "supplier": purchase.supplier if offset.party_requirement == "SUPPLIER" else None})
    return services._save_draft(
        actor=actor, token=uuid4(), lines=lines, source_kind=SOURCE_KIND, source_identifier=origin,
        values={"journal": config.journal, "period": period, "accounting_date": date, "document_date": date,
                "description": f"Engagement · {purchase.number}", "document_reference": order.number},
    )
