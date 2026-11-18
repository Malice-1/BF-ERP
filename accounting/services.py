"""Audited accounting commands. Lock order: profile -> period -> entry -> sequence."""
from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from workflow.activity import write_log
from sales.models import IssuerConfiguration
from .models import (AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal,
    EntrySequence, JournalEntry, JournalEntryLine, AccountingEvent)


CURRENT_CHART_REFERENCE = "Plan de comptes actuel"


def require(actor, permission):
    if not actor.is_authenticated or not actor.is_active or not actor.has_perm("accounting." + permission):
        raise PermissionDenied("Droit comptable insuffisant.")


def profile_lock():
    profile, _ = AccountingProfile.objects.select_for_update().get_or_create(pk=1)
    return profile


def audit(actor, obj, action, entry=None, **details):
    record = AccountingEvent.objects.create(actor=actor, actor_name=actor.get_username() if actor else "Système", action=action,
        object_type=obj._meta.label_lower, object_identifier=str(obj.pk), entry=entry, details=details)
    write_log(record, "created", {"action": action, "object": record.object_type,
        "id": record.object_identifier, **details}, "default", actor=actor)


@transaction.atomic
def configure_profile(*, actor, issuer, framework, chart_reference, revision):
    require(actor, "change_accountingprofile")
    profile = profile_lock()
    if revision != profile.revision:
        raise ValidationError("Le cadre a changé. Rechargez la page.")
    if JournalEntry.objects.filter(status="POSTED").exists() and (issuer.pk != profile.issuer_id or framework != profile.framework):
        raise ValidationError("L’entité et le cadre ne peuvent plus changer après une première validation.")
    profile.issuer, profile.framework = issuer, framework
    profile.chart_reference = chart_reference.strip() or CURRENT_CHART_REFERENCE
    profile.full_clean()
    profile.revision += 1
    profile.save()
    audit(actor, profile, "Cadre comptable configuré", framework=framework, reference=chart_reference)
    return profile


@transaction.atomic
def save_account(*, actor, values, pk=None):
    require(actor, "change_account" if pk else "add_account")
    profile_lock()
    allowed = {"code", "label", "postable", "is_active", "party_requirement", "source_reference"}
    if set(values) - allowed:
        raise ValidationError("Champ de compte non autorisé.")
    account = Account.objects.select_for_update().get(pk=pk) if pk else Account()
    if pk and account.journalentryline_set.exists() and any(values.get(key, getattr(account, key)) != getattr(account, key)
            for key in ("code", "postable", "party_requirement")):
        raise ValidationError("Le code, le type d’imputation et le type de tiers d’un compte utilisé sont protégés.")
    for name, value in values.items():
        setattr(account, name, value)
    account.full_clean()
    account.save()
    audit(actor, account, "Compte enregistré", values=values)
    return account


@transaction.atomic
def save_journal(*, actor, values, pk=None):
    require(actor, "change_journal" if pk else "add_journal")
    profile_lock()
    if set(values) - {"code", "label", "kind", "is_active"}:
        raise ValidationError("Champ de journal non autorisé.")
    journal = Journal.objects.select_for_update().get(pk=pk) if pk else Journal()
    if pk and journal.journalentry_set.exists() and any(values.get(f, getattr(journal, f)) != getattr(journal, f) for f in ("code", "kind")):
        raise ValidationError("Le code et le type d’un journal utilisé sont protégés.")
    for key, value in values.items():
        setattr(journal, key, value)
    journal.full_clean()
    journal.save()
    audit(actor, journal, "Journal enregistré", **values)
    return journal


@transaction.atomic
def create_year(*, actor, code, start_date, end_date):
    require(actor, "add_fiscalyear")
    profile_lock()
    if FiscalYear.objects.filter(start_date__lte=end_date, end_date__gte=start_date).exists():
        raise ValidationError("Cet exercice chevauche un exercice existant.")
    year = FiscalYear(code=code, start_date=start_date, end_date=end_date)
    year.full_clean()
    year.save()
    audit(actor, year, "Exercice créé", start=str(start_date), end=str(end_date))
    return year


@transaction.atomic
def create_period(*, actor, fiscal_year, label, start_date, end_date):
    require(actor, "add_accountingperiod")
    profile_lock()
    year = FiscalYear.objects.select_for_update().get(pk=fiscal_year.pk)
    if not year.is_open or not year.start_date <= start_date <= end_date <= year.end_date:
        raise ValidationError("La période doit appartenir à un exercice ouvert et respecter ses dates.")
    if year.periods.filter(start_date__lte=end_date, end_date__gte=start_date).exists():
        raise ValidationError("Cette période chevauche une période existante.")
    period = AccountingPeriod(fiscal_year=year, label=label, start_date=start_date, end_date=end_date)
    period.full_clean()
    period.save()
    audit(actor, period, "Période créée", start=str(start_date), end=str(end_date))
    return period


@transaction.atomic
def set_period_open(*, actor, pk, is_open, reason):
    require(actor, "reopen_accountingperiod" if is_open else "lock_accountingperiod")
    profile_lock()
    period = AccountingPeriod.objects.select_for_update().get(pk=pk)
    if not reason.strip():
        raise ValidationError("La justification est obligatoire.")
    if is_open and not period.fiscal_year.is_open:
        raise ValidationError("L’exercice est fermé.")
    period.is_open = is_open
    period.save(update_fields=["is_open"])
    audit(actor, period, "Période rouverte" if is_open else "Période fermée", reason=reason)
    return period


ENTRY_FIELDS = {"journal", "period", "accounting_date", "document_date", "description", "document_reference"}
LINE_FIELDS = {"account", "description", "debit", "credit", "customer", "supplier"}


def line_values(line):
    return {key: getattr(line, key) for key in LINE_FIELDS}


def money(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result != result.quantize(Decimal("0.01")):
            raise ValueError
        return result
    except (ValueError, ArithmeticError) as cause:
        raise ValidationError("Les montants doivent être positifs et comporter au plus deux décimales.") from cause


def validate_lines(lines, reversal=False):
    for line in lines:
        line.debit, line.credit = money(line.debit), money(line.credit)
        line.full_clean(validate_constraints=False)
        account = Account.objects.select_for_update().get(pk=line.account_id)
        if not account.postable or (not account.is_active and not reversal):
            raise ValidationError(f"Le compte {account.code} n’est pas un compte d’imputation actif.")
        if account.party_requirement == "CUSTOMER" and not line.customer_id:
            raise ValidationError(f"Un client est obligatoire pour le compte {account.code}.")
        if account.party_requirement == "SUPPLIER" and not line.supplier_id:
            raise ValidationError(f"Un fournisseur est obligatoire pour le compte {account.code}.")
        if account.party_requirement == "CUSTOMER" and line.supplier_id or account.party_requirement == "SUPPLIER" and line.customer_id:
            raise ValidationError("Le type de tiers ne correspond pas au compte.")
        line.account = account


@transaction.atomic
def save_draft(*, actor, values, lines, token, pk=None, revision=0):
    require(actor, "change_journalentry" if pk else "add_journalentry")
    profile_lock()
    return _save_draft(actor=actor, values=values, lines=lines, token=token, pk=pk, revision=revision)


def _save_draft(*, actor, values, lines, token, pk=None, revision=0, source_kind="MANUAL", source_identifier="",
                source_invoice=None):
    if set(values) - ENTRY_FIELDS or any(set(line) - LINE_FIELDS for line in lines):
        raise ValidationError("Champ d’écriture non autorisé.")
    if not pk:
        existing = JournalEntry.objects.filter(idempotency_key=token).first()
        if existing:
            if existing.created_by_id != getattr(actor, "pk", None):
                raise ValidationError("Cette clé de saisie est déjà utilisée.")
            def normal(row):
                return {"account": row["account"].pk, "description": row.get("description", ""),
                    "debit": money(row.get("debit", 0)), "credit": money(row.get("credit", 0)),
                    "customer": getattr(row.get("customer"), "pk", None),
                    "supplier": getattr(row.get("supplier"), "pk", None)}
            requested = [normal(row) for row in lines]
            saved = [normal(line_values(row)) for row in existing.lines.all()]
            if any(getattr(existing, key) != value for key, value in values.items()) or requested != saved:
                raise ValidationError("Cette clé correspond à une autre saisie ; rechargez le formulaire.")
            return existing
    entry = JournalEntry.objects.select_for_update().get(pk=pk) if pk else JournalEntry(
        created_by=actor, idempotency_key=token, source_kind=source_kind,
        source_identifier=source_identifier, source_invoice=source_invoice)
    if entry.status != "DRAFT" or entry.reversal_of_id:
        raise ValidationError("Cette écriture ne peut pas être modifiée.")
    if pk and (entry.revision != revision or entry.idempotency_key != token):
        raise ValidationError("L’écriture a changé. Rechargez la page.")
    for key, value in values.items():
        setattr(entry, key, value)
    period = AccountingPeriod.objects.select_for_update().get(pk=entry.period_id)
    if not period.is_open or not period.fiscal_year.is_open or not period.start_date <= entry.accounting_date <= period.end_date:
        raise ValidationError("La date doit appartenir à une période ouverte.")
    if not entry.journal.is_active:
        raise ValidationError("Ce journal est inactif.")
    if not 2 <= len(lines) <= 200:
        raise ValidationError("Une écriture doit contenir de 2 à 200 lignes.")
    entry.full_clean()
    entry.save()
    prepared = [JournalEntryLine(entry=entry, position=i, **row) for i, row in enumerate(lines, 1)]
    validate_lines(prepared)
    JournalEntryLine._base_manager.filter(entry=entry).delete()
    for line in prepared:
        line.save()
    entry.debit_total = sum((line.debit for line in prepared), Decimal(0))
    entry.credit_total = sum((line.credit for line in prepared), Decimal(0))
    entry.revision += 1
    entry.full_clean()
    entry.save()
    audit(actor, entry, "Brouillon enregistré", entry=entry, revision=entry.revision,
        debit=str(entry.debit_total), credit=str(entry.credit_total),
        **({"source_kind": entry.source_kind, "source_identifier": entry.source_identifier}
           if entry.source_identifier else {}))
    return entry


def _post(profile, entry, actor):
    period = AccountingPeriod.objects.select_for_update().get(pk=entry.period_id)
    year = FiscalYear.objects.select_for_update().get(pk=period.fiscal_year_id)
    journal = Journal.objects.select_for_update().get(pk=entry.journal_id)
    if not profile.issuer_id:
        raise ValidationError("Configurez l’entité comptable avant de valider une écriture.")
    profile.issuer = IssuerConfiguration.objects.select_for_update().get(pk=profile.issuer_id)
    if not profile.issuer.name.strip() or not profile.issuer.legal_id.strip():
        raise ValidationError("L’identité légale de l’entité comptable est incomplète.")
    origin = JournalEntry.objects.filter(status="POSTED").order_by("pk").first()
    if origin and origin.issuer_snapshot["legal_id"] != profile.issuer.legal_id:
        raise ValidationError("Une autre identité légale exige une comptabilité distincte.")
    if not period.is_open or not year.is_open or not period.start_date <= entry.accounting_date <= period.end_date:
        raise ValidationError("La période ou l’exercice est fermé, ou la date est hors période.")
    if not journal.is_active or not entry.document_reference.strip():
        raise ValidationError("Un journal actif et une référence de pièce justificative sont obligatoires.")
    lines = list(entry.lines.select_related("account", "customer", "supplier"))
    if len(lines) < 2:
        raise ValidationError("Deux lignes au moins sont requises.")
    validate_lines(lines, reversal=bool(entry.reversal_of_id))
    debit, credit = sum((line.debit for line in lines), Decimal(0)), sum((line.credit for line in lines), Decimal(0))
    if debit != credit or debit <= 0:
        raise ValidationError(f"L’écriture n’est pas équilibrée : débit {debit}, crédit {credit}.")
    sequence, _ = EntrySequence.objects.select_for_update().get_or_create(journal=journal, fiscal_year=year)
    if sequence.last_date and entry.accounting_date < sequence.last_date:
        raise ValidationError("La date précède la dernière écriture de ce journal/exercice. Utilisez une date comptable autorisée et conservez la date de pièce originale.")
    for line in lines:
        if entry.reversal_of_id:
            original = entry.reversal_of.lines.get(position=line.position)
            if (line.account_id, line.debit, line.credit, line.customer_id, line.supplier_id) != (
                    original.account_id, original.credit, original.debit, original.customer_id, original.supplier_id):
                raise ValidationError("La contrepassation ne correspond pas à l’écriture initiale.")
            line.account_snapshot, line.party_snapshot = original.account_snapshot, original.party_snapshot
        else:
            line.account_snapshot = {"code": line.account.code, "label": line.account.label,
                "party_requirement": line.account.party_requirement}
            party = line.customer or line.supplier
            line.party_snapshot = {"kind": "CUSTOMER" if line.customer_id else "SUPPLIER", "id": party.pk,
                "code": party.code, "name": party.name} if party else {}
        line.save(update_fields=["account_snapshot", "party_snapshot"])
    sequence.last_number += 1
    sequence.last_date = entry.accounting_date
    sequence.save()
    entry.number = f"{journal.code}-{year.code}-{sequence.last_number:06d}"
    entry.issuer_snapshot = {"name": profile.issuer.name, "legal_id": profile.issuer.legal_id,
        "framework": profile.framework, "chart_reference": profile.chart_reference or CURRENT_CHART_REFERENCE,
        "profile_revision": profile.revision}
    entry.journal_snapshot = {"code": journal.code, "label": journal.label, "kind": journal.kind}
    entry.fiscal_snapshot = {"year": year.code, "period": period.label}
    entry.debit_total, entry.credit_total = debit, credit
    entry.status = "POSTED"
    entry.posted_at, entry.posted_by, entry.posted_by_name = timezone.now(), actor, actor.get_username()
    entry.revision += 1
    entry.full_clean()
    entry.save()
    audit(actor, entry, "Écriture validée", entry=entry, number=entry.number, debit=str(debit), credit=str(credit))
    return entry


@transaction.atomic
def post_entry(*, actor, pk, revision):
    require(actor, "post_journalentry")
    profile = profile_lock()
    entry = JournalEntry.objects.select_for_update().get(pk=pk)
    if entry.status == "POSTED":
        if revision not in (entry.revision, entry.revision - 1):
            raise ValidationError("Révision périmée.")
        return entry
    if entry.revision != revision:
        raise ValidationError("L’écriture a changé. Rechargez la page.")
    return _post(profile, entry, actor)


@transaction.atomic
def reverse_entry(*, actor, pk, period, accounting_date, reason, token):
    require(actor, "reverse_journalentry")
    profile = profile_lock()
    original = JournalEntry.objects.select_for_update().get(pk=pk)
    if original.status != "POSTED" or original.reversal_of_id:
        raise ValidationError("Seule une écriture d’origine validée peut être contre-passée une fois.")
    existing = JournalEntry.objects.filter(reversal_of=original).first()
    if existing:
        if (existing.period_id, existing.accounting_date, existing.reversal_reason, existing.idempotency_key) != (period.pk, accounting_date, reason.strip(), token):
            raise ValidationError("Cette écriture a déjà une contrepassation différente.")
        return existing
    if not reason.strip() or accounting_date < original.accounting_date:
        raise ValidationError("Un motif et une date comptable non antérieure à l’origine sont requis.")
    entry = JournalEntry.objects.create(journal=original.journal, period=period, accounting_date=accounting_date,
        document_date=timezone.localdate(), description=f"Contrepassation {original.number}",
        document_reference=original.number, idempotency_key=token, reversal_of=original,
        reversal_reason=reason.strip(), source_kind="REVERSAL", source_identifier=str(original.pk), created_by=actor)
    for row in original.lines.all():
        JournalEntryLine.objects.create(entry=entry, position=row.position, account=row.account,
            description=row.description, debit=row.credit, credit=row.debit, customer=row.customer, supplier=row.supplier)
    entry = _post(profile, entry, actor)
    audit(actor, entry, "Contrepassation validée", entry=entry, original=original.number, reason=reason)
    return entry
