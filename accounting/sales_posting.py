from collections import defaultdict
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from . import services
from .models import AccountingPeriod, JournalEntry, SalesBudgetProductAccount, SalesPostingConfiguration


SOURCE_KIND = "SALES_INVOICE"


@transaction.atomic
def configure(*, actor, settings=None, mapping=None):
    services.require(actor, "change_salespostingconfiguration")
    services.profile_lock()
    if settings is not None:
        config, _ = SalesPostingConfiguration.objects.update_or_create(pk=1, defaults=settings)
        services.audit(actor, config, "Paramétrage des imputations des ventes", enabled=config.enabled,
                       journal=config.journal_id, receivable_account=config.receivable_account_id,
                       tax_account=config.tax_account_id)
    if mapping is not None:
        assigned, _ = SalesBudgetProductAccount.objects.update_or_create(
            product=mapping["product"], defaults={"account": mapping["account"]})
        services.audit(actor, assigned, "Imputation de vente du produit budgétaire",
                       product=assigned.product_id, account=assigned.account_id)


def locked_configuration():
    if not SalesPostingConfiguration.objects.filter(pk=1, enabled=True).exists():
        return None
    services.profile_lock()
    return SalesPostingConfiguration.objects.filter(pk=1, enabled=True).select_related(
        "journal", "receivable_account", "tax_account").first()


def create_invoice_draft(*, actor, config, invoice, invoice_lines, customer):
    """Generate the draft in the invoice issuance transaction under the accounting profile lock."""
    if config is None or not invoice.total:
        return
    origin = str(invoice.pk)
    existing = JournalEntry.objects.filter(source_kind=SOURCE_KIND, source_identifier=origin).first()
    if existing is not None:
        return existing
    if config.journal.kind != "SALE":
        raise ValidationError("Le journal configuré doit être de type Ventes.")

    amounts = defaultdict(Decimal)
    for line in invoice_lines:
        if not line.subtotal:
            continue
        if not line.budget_product_id:
            raise ValidationError(f"Renseignez le produit budgétaire de la ligne « {line.description} » pour l’imputer.")
        amounts[line.budget_product] += line.subtotal

    accounts = {
        mapping.product_id: mapping.account
        for mapping in SalesBudgetProductAccount.objects.filter(product__in=amounts).select_related("account")
    }
    missing = [str(product) for product in amounts if product.pk not in accounts]
    if missing:
        raise ValidationError("Compte de produit manquant pour les produits budgétaires suivants : " + ", ".join(missing))
    if invoice.tax_total and not config.tax_account_id:
        raise ValidationError("Configurez le compte de TVA collectée avant d’émettre cette facture.")
    if any(account.pk in {config.receivable_account_id, config.tax_account_id} for account in accounts.values()):
        raise ValidationError("Les comptes de produit doivent être distincts des comptes clients et de TVA.")
    if config.receivable_account_id == config.tax_account_id:
        raise ValidationError("Les comptes clients et de TVA doivent être distincts.")

    date = invoice.issue_date
    period = AccountingPeriod.objects.filter(start_date__lte=date, end_date__gte=date,
        is_open=True, fiscal_year__is_open=True).first()
    if period is None:
        raise ValidationError("Aucune période comptable ouverte à la date de la facture.")
    lines = [{"account": config.receivable_account, "description": str(customer)[:255],
              "debit": invoice.total, "customer": customer}]
    lines.extend({"account": accounts[product.pk], "description": str(product)[:255], "credit": amount}
                 for product, amount in amounts.items())
    if invoice.tax_total:
        lines.append({"account": config.tax_account, "description": "TVA collectée", "credit": invoice.tax_total})
    if sum(line.get("credit", 0) for line in lines) != invoice.total:
        raise ValidationError("Les montants de la facture ne permettent pas d’équilibrer l’écriture de vente.")
    return services._save_draft(
        actor=actor, token=uuid4(), lines=lines, source_kind=SOURCE_KIND, source_identifier=origin, source_invoice=invoice,
        values={"journal": config.journal, "period": period, "accounting_date": date, "document_date": date,
                "description": f"Facture de vente · {invoice.number}", "document_reference": invoice.number},
    )
