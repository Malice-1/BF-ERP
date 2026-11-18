from decimal import Decimal, localcontext

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import BudgetEntry, FrameworkContract, FrameworkContractPrice


def available_contracts():
    date = timezone.localdate()
    return FrameworkContract.objects.filter(is_active=True, start_date__lte=date, end_date__gte=date)


def require_available(contract):
    if not contract.is_active or not contract.start_date <= timezone.localdate() <= contract.end_date:
        raise ValidationError("Le contrat-cadre doit être actif et en cours de validité.")


def usage(contract):
    totals = {"reserved": Decimal(0), "committed": Decimal(0)}
    entries = BudgetEntry.objects.filter(snapshot__submission__purchase_request__framework_contract=contract,
        state__in=totals).values_list("state", "amount")
    with localcontext() as context:
        context.prec = 50
        for state, amount in entries:
            totals[state] += amount
    return totals


def price_for(contract, product_id):
    price = contract.prices.filter(product_id=product_id, is_active=True).first()
    if price is None:
        raise ValidationError("Ce produit ne figure pas au catalogue actif du contrat-cadre.")
    return price


def reserve_for_submission(purchase, lines):
    contract = FrameworkContract.objects.select_for_update().get(pk=purchase.framework_contract_id)
    require_available(contract)
    if contract.supplier_id != purchase.supplier_id:
        raise ValidationError("Le fournisseur de la demande doit correspondre au contrat-cadre.")
    for line in lines:
        price = price_for(contract, line.detailed_product_id)
        if (line.unit_price, line.vat_rate) != (price.unit_price, price.vat_rate):
            raise ValidationError(f"Le tarif de « {line.detailed_product} » a changé. Réenregistrez la ligne avant de soumettre la demande.")
    if contract.ceiling is not None:
        remaining = contract.ceiling - sum(usage(contract).values())
        requested = sum(line.total_tvac for line in lines)
        if requested > remaining:
            raise ValidationError(f"Plafond du contrat-cadre dépassé. Disponible : {remaining:.2f} EUR TVAC. Demande : {requested:.2f} EUR TVAC.")
    return {"reference": contract.reference, "title": contract.title}


@transaction.atomic
def save_contract(*, actor, values, pk=None):
    if not actor.has_perm("purchasing.change_frameworkcontract" if pk else "purchasing.add_frameworkcontract"):
        raise PermissionDenied
    contract = FrameworkContract.objects.select_for_update().get(pk=pk) if pk else FrameworkContract()
    previous_supplier = contract.supplier_id
    for key, value in values.items():
        setattr(contract, key, value)
    if pk and previous_supplier != contract.supplier_id and contract.purchase_requests.exists():
        raise ValidationError("Le fournisseur est protégé dès qu’une demande utilise ce contrat-cadre.")
    if pk and contract.ceiling is not None and contract.ceiling < sum(usage(contract).values()):
        raise ValidationError("Le plafond est inférieur aux montants déjà réservés et engagés.")
    contract.full_clean()
    contract.save()
    return contract


@transaction.atomic
def save_price(*, actor, contract_id, values):
    if not actor.has_perm("purchasing.change_frameworkcontract"):
        raise PermissionDenied
    contract = FrameworkContract.objects.select_for_update().get(pk=contract_id)
    price = contract.prices.filter(product=values["product"]).first()
    if price is None:
        price = FrameworkContractPrice(contract=contract, product=values["product"])
    for key in ("unit_price", "vat_rate", "is_active"):
        setattr(price, key, values[key])
    price.full_clean()
    price.save()
    return price
