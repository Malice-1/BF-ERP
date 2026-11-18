"""General ledger, separate from purchase budget commitments."""
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class GuardedQuerySet(models.QuerySet):
    def update(self, **kwargs):
        if len(kwargs) == 1 and next(iter(kwargs)) in {"actor", "created_by", "posted_by", "approved_by", "reviewed_by"} and next(iter(kwargs.values())) is None:
            return super().update(**kwargs)
        raise ValidationError("Utilisez les services comptables pour modifier ces données.")

    def delete(self):
        raise ValidationError("L’historique comptable ne peut pas être supprimé.")

    def bulk_create(self, objs, *args, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("Le remplacement de données comptables est interdit.")
        return super().bulk_create(objs, *args, **kwargs)


class GuardedModel(models.Model):
    objects = GuardedQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError("Désactivez ou contre-passez cet enregistrement pour conserver sa trace.")


class AccountingProfile(GuardedModel):
    issuer = models.OneToOneField("sales.IssuerConfiguration", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Entité existante")
    framework = models.CharField("Cadre", max_length=15, default="PUBLIC", choices=[
        ("PUBLIC", "Plan spécifique à un organisme public"), ("ENTERPRISE", "PCMN entreprises"),
        ("NONPROFIT", "PCMN associations et fondations")])
    chart_reference = models.CharField("Référence officielle du plan applicable", max_length=500, blank=True)
    chart_manifest = models.JSONField(default=list, blank=True)
    approval_note = models.TextField("Justification de la validation du cadre et du plan", blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    approved_by_name = models.CharField(max_length=150, blank=True)
    approved_issuer_snapshot = models.JSONField(default=dict, blank=True)
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ("view", "change")
        verbose_name = "cadre comptable"
        verbose_name_plural = "cadre comptable"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="acct_single_profile")]


class Account(GuardedModel):
    code = models.CharField("Compte", max_length=12, unique=True,
        validators=[RegexValidator(r"^[0-9]{1,12}$", "Le code doit contenir de 1 à 12 chiffres.")])
    label = models.CharField("Libellé", max_length=255)
    postable = models.BooleanField("Compte d’imputation", default=True)
    is_active = models.BooleanField("Actif", default=True)
    party_requirement = models.CharField("Tiers requis", max_length=10, default="NONE",
        choices=[("NONE", "Aucun"), ("CUSTOMER", "Client"), ("SUPPLIER", "Fournisseur")])
    source_reference = models.CharField("Référence du plan", max_length=500, blank=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "compte général"
        verbose_name_plural = "plan de comptes"
        default_permissions = ("view", "add", "change")

    def __str__(self):
        return f"{self.code} — {self.label}"


class FiscalYear(GuardedModel):
    code = models.CharField("Exercice", max_length=12, unique=True,
        validators=[RegexValidator(r"^[A-Z0-9-]{1,12}$", "Utilisez des lettres majuscules, chiffres ou tirets.")])
    start_date = models.DateField("Du")
    end_date = models.DateField("Au")
    is_open = models.BooleanField("Ouvert aux écritures", default=True)

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "exercice comptable"
        verbose_name_plural = "exercices comptables"
        default_permissions = ("view", "add")
        constraints = [models.CheckConstraint(condition=models.Q(start_date__lte=models.F("end_date")), name="acct_year_dates")]

    def __str__(self):
        return self.code


class AccountingPeriod(GuardedModel):
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods", verbose_name="Exercice")
    label = models.CharField("Période", max_length=100)
    start_date = models.DateField("Du")
    end_date = models.DateField("Au")
    is_open = models.BooleanField("Ouverte", default=True)

    class Meta:
        ordering = ["start_date"]
        verbose_name = "période comptable"
        verbose_name_plural = "périodes comptables"
        default_permissions = ("view", "add")
        permissions = [("lock_accountingperiod", "Fermer les périodes aux écritures"),
                       ("reopen_accountingperiod", "Rouvrir une période avec justification")]
        constraints = [models.CheckConstraint(condition=models.Q(start_date__lte=models.F("end_date")), name="acct_period_dates"),
            models.UniqueConstraint(fields=["fiscal_year", "label"], name="acct_period_label")]

    def __str__(self):
        return f"{self.fiscal_year} — {self.label}"


class Journal(GuardedModel):
    code = models.CharField("Code", max_length=8, unique=True,
        validators=[RegexValidator(r"^[A-Z0-9]{1,8}$", "Utilisez de 1 à 8 lettres majuscules ou chiffres.")])
    label = models.CharField("Libellé", max_length=100)
    kind = models.CharField("Type", max_length=10, choices=[("PURCHASE", "Achats"), ("SALE", "Ventes"),
        ("BANK", "Financier"), ("GENERAL", "Opérations diverses")])
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "journal comptable"
        verbose_name_plural = "journaux comptables"
        default_permissions = ("view", "add", "change")

    def __str__(self):
        return f"{self.code} — {self.label}"


class EntrySequence(GuardedModel):
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT)
    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT)
    last_number = models.PositiveIntegerField(default=0)
    last_date = models.DateField(null=True)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["journal", "fiscal_year"], name="acct_sequence_unique")]


class PurchasePostingConfiguration(GuardedModel):
    enabled = models.BooleanField("Générer les écritures à la validation des DA", default=False)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, verbose_name="Journal des engagements")
    offset_account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Compte de contrepartie")

    class Meta:
        default_permissions = ("change",)
        verbose_name = "paramétrage des imputations des demandes d’achat"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="acct_single_purchase_posting")]


class BudgetProductAccount(GuardedModel):
    product = models.OneToOneField("budgeting.BudgetProduct", on_delete=models.PROTECT, verbose_name="Produit budgétaire")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Compte d’imputation")

    class Meta:
        default_permissions = ()


class SalesPostingConfiguration(GuardedModel):
    enabled = models.BooleanField("Générer les écritures à l’émission des factures", default=False)
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, verbose_name="Journal des ventes")
    receivable_account = models.ForeignKey(Account, on_delete=models.PROTECT,
        related_name="+", verbose_name="Compte clients")
    tax_account = models.ForeignKey(Account, on_delete=models.PROTECT, null=True, blank=True,
        related_name="+", verbose_name="Compte de TVA collectée")

    class Meta:
        default_permissions = ("change",)
        verbose_name = "paramétrage des imputations des ventes"
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="acct_single_sales_posting")]


class SalesBudgetProductAccount(GuardedModel):
    product = models.OneToOneField("budgeting.BudgetProduct", on_delete=models.PROTECT, verbose_name="Produit budgétaire")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Compte de produit")

    class Meta:
        default_permissions = ()


class JournalEntry(GuardedModel):
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, verbose_name="Journal")
    period = models.ForeignKey(AccountingPeriod, on_delete=models.PROTECT, verbose_name="Période")
    accounting_date = models.DateField("Date comptable", default=timezone.localdate)
    document_date = models.DateField("Date de pièce", default=timezone.localdate)
    description = models.CharField("Libellé", max_length=255)
    document_reference = models.CharField("Référence de pièce justificative", max_length=255, blank=True)
    currency = models.CharField("Devise", max_length=3, default="EUR", choices=[("EUR", "EUR")])
    status = models.CharField("État", max_length=10, default="DRAFT", choices=[("DRAFT", "Brouillon"), ("POSTED", "Validée")])
    number = models.CharField("Numéro définitif", max_length=50, null=True, blank=True, unique=True)
    debit_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    credit_total = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    revision = models.PositiveIntegerField(default=0)
    idempotency_key = models.UUIDField(unique=True)
    source_kind = models.CharField(max_length=30, default="MANUAL")
    source_identifier = models.CharField(max_length=100, blank=True)
    source_invoice = models.ForeignKey("sales.SalesInvoice", null=True, blank=True, on_delete=models.PROTECT)
    source_document = models.ForeignKey("sales.InvoiceDocument", null=True, blank=True, on_delete=models.PROTECT)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversal")
    reversal_reason = models.CharField(max_length=255, blank=True)
    issuer_snapshot = models.JSONField(default=dict, blank=True)
    journal_snapshot = models.JSONField(default=dict, blank=True)
    fiscal_snapshot = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="accounting_entries")
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="accounting_postings")
    posted_by_name = models.CharField(max_length=150, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "écriture comptable"
        verbose_name_plural = "écritures comptables"
        default_permissions = ("view", "add", "change")
        permissions = [("post_journalentry", "Valider les écritures comptables"),
                       ("reverse_journalentry", "Contre-passer les écritures validées")]
        constraints = [
            models.UniqueConstraint(fields=["source_kind", "source_identifier"], condition=~models.Q(source_identifier=""), name="acct_unique_origin"),
            models.CheckConstraint(condition=models.Q(currency="EUR"), name="acct_eur_only"),
            models.CheckConstraint(condition=models.Q(status="DRAFT", number__isnull=True, posted_at__isnull=True) |
                models.Q(status="POSTED", number__isnull=False, posted_at__isnull=False, debit_total=models.F("credit_total"), debit_total__gt=0), name="acct_posted_metadata"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, status="POSTED").exists():
            raise ValidationError("Une écriture validée est immuable. Utilisez une contrepassation.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.number or f"Brouillon {self.pk}"


class JournalEntryLine(GuardedModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveIntegerField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, verbose_name="Compte")
    description = models.CharField("Libellé de ligne", max_length=255, blank=True)
    debit = models.DecimalField("Débit EUR", max_digits=18, decimal_places=2, default=0)
    credit = models.DecimalField("Crédit EUR", max_digits=18, decimal_places=2, default=0)
    customer = models.ForeignKey("sales.Customer", null=True, blank=True, on_delete=models.PROTECT, verbose_name="Client")
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT, verbose_name="Fournisseur")
    account_snapshot = models.JSONField(default=dict, blank=True)
    party_snapshot = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["position"]
        default_permissions = ()
        constraints = [
            models.UniqueConstraint(fields=["entry", "position"], name="acct_line_position"),
            models.CheckConstraint(condition=models.Q(debit__gt=0, credit=0) | models.Q(credit__gt=0, debit=0), name="acct_line_one_side"),
            models.CheckConstraint(condition=models.Q(customer__isnull=True) | models.Q(supplier__isnull=True), name="acct_line_one_party"),
        ]

    def clean(self):
        super().clean()
        if self.debit is None or self.credit is None:
            return
        if not ((self.debit > 0 and self.credit == 0) or (self.credit > 0 and self.debit == 0)):
            raise ValidationError("Chaque ligne doit comporter un débit OU un crédit strictement positif.")
        if self.customer_id and self.supplier_id:
            raise ValidationError("Une ligne ne peut pas avoir deux tiers.")

    def save(self, *args, **kwargs):
        if JournalEntry.objects.filter(pk=self.entry_id, status="POSTED").exists():
            raise ValidationError("Les lignes validées sont immuables.")
        if self.pk and type(self).objects.filter(pk=self.pk).exclude(entry_id=self.entry_id).exists():
            raise ValidationError("Une ligne ne peut pas changer d’écriture.")
        return super().save(*args, **kwargs)


class AccountingEvent(GuardedModel):
    entry = models.ForeignKey(JournalEntry, null=True, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_identifier = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        default_permissions = ()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Le journal comptable est immuable.")
        return super().save(*args, **kwargs)


class SupplierInvoice(GuardedModel):
    origin = models.CharField("Origine", max_length=8, default="PEPPOL",
        choices=[("PEPPOL", "Import Peppol"), ("MANUAL", "Saisie manuelle")])
    checksum = models.CharField(max_length=64, unique=True, null=True, blank=True)
    business_key = models.CharField(max_length=64, null=True, unique=True, blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    storage_path = models.CharField(max_length=500, blank=True)
    invoice_number = models.CharField("Numéro fournisseur", max_length=255, blank=True)
    issue_date = models.DateField("Date de facture", null=True, blank=True)
    due_date = models.DateField("Échéance", null=True, blank=True)
    currency = models.CharField("Devise", max_length=3, blank=True)
    subtotal = models.DecimalField("HT", max_digits=20, decimal_places=2, null=True, blank=True)
    tax_total = models.DecimalField("TVA", max_digits=20, decimal_places=2, null=True, blank=True)
    total = models.DecimalField("TTC", max_digits=20, decimal_places=2, null=True, blank=True)
    payable = models.DecimalField("À payer", max_digits=20, decimal_places=2, null=True, blank=True)
    extracted_data = models.JSONField(default=dict)
    supplier = models.ForeignKey("suppliers.Supplier", null=True, blank=True, on_delete=models.PROTECT,
        verbose_name="Fournisseur rapproché")
    status = models.CharField("Revue", max_length=12, default="RECEIVED", choices=[
        ("RECEIVED", "À vérifier"), ("REVIEWED", "Approuvée"), ("REJECTED", "Rejetée")])
    revision = models.PositiveIntegerField(default=0)
    review_note = models.TextField("Note de revue", blank=True)
    review_snapshot = models.JSONField(default=dict, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="supplier_invoice_reviews")
    reviewed_by_name = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="supplier_invoice_imports")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "facture fournisseur"
        verbose_name_plural = "factures fournisseurs"
        default_permissions = ("view", "add", "change")
        permissions = [("import_supplierinvoice", "Importer les factures fournisseurs XML"),
            ("review_supplierinvoice", "Approuver ou rejeter les factures fournisseurs"),
            ("download_supplierinvoice", "Télécharger les XML fournisseurs"),
            ("revalidate_supplierinvoice", "Revalider les XML fournisseurs")]

    PROVENANCE_FIELDS = ("origin", "checksum", "business_key", "original_filename", "storage_path", "created_at")
    INVOICE_FIELDS = ("invoice_number", "issue_date", "due_date", "currency", "subtotal", "tax_total",
                      "total", "payable", "extracted_data")

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            immutable = self.PROVENANCE_FIELDS + (self.INVOICE_FIELDS if old.origin == "PEPPOL" else ())
            if any(getattr(old, key) != getattr(self, key) for key in immutable):
                raise ValidationError("L’origine de la facture et les données importées sont immuables.")
            if old.status != "RECEIVED":
                raise ValidationError("La revue de cette facture est déjà terminée.")
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number or f"Facture fournisseur {self.pk}"


class SupplierInvoiceValidation(GuardedModel):
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name="validations")
    status = models.CharField(max_length=12, choices=[("VALID", "Conforme"), ("INVALID", "Non conforme"), ("UNAVAILABLE", "Validation indisponible")])
    details = models.JSONField(default=list)
    rules_version = models.CharField(max_length=150, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-pk"]
        default_permissions = ()

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Les résultats de validation sont conservés sans réécriture.")
        return super().save(*args, **kwargs)
