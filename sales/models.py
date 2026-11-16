from decimal import Decimal, ROUND_HALF_UP
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone


MONEY = Decimal("0.01")
country_code = RegexValidator(r"^[A-Z]{2}$", "Utilisez un code pays ISO à deux lettres majuscules.")


def rounded(value):
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class ProtectedQuerySet(models.QuerySet):
    def bulk_create(self, objs, *args, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("La réécriture de l’historique est interdite.")
        return super().bulk_create(objs, *args, **kwargs)

    def update(self, **kwargs):
        # Django may detach a deleted user's nullable identity FK. Historical
        # names remain stored in the event; other bulk mutations are forbidden.
        if len(kwargs) == 1 and next(iter(kwargs)) in ("actor", "actor_id", "created_by", "created_by_id") and next(iter(kwargs.values())) is None:
            return super().update(**kwargs)
        raise ValidationError("Utilisez les opérations métier pour modifier les données de vente.")

    def delete(self):
        raise ValidationError("L’historique de vente ne peut pas être supprimé.")


class AppendOnlyModel(models.Model):
    objects = ProtectedQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Cet enregistrement fait partie de l’historique immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Cet enregistrement fait partie de l’historique immuable.")


class InvoiceFormat(models.TextChoices):
    PDF = "PDF", "PDF"
    XML = "PEPPOL_XML", "XML Peppol"


class Customer(models.Model):
    code = models.CharField("Code", max_length=50, unique=True)
    name = models.CharField("Raison sociale / nom", max_length=255)
    street = models.CharField("Rue et numéro", max_length=255, blank=True)
    zip_code = models.CharField("Code postal", max_length=20, blank=True)
    city = models.CharField("Ville", max_length=100, blank=True)
    country = models.CharField("Pays (ISO)", max_length=2, default="BE", validators=[country_code])
    vat_number = models.CharField("Numéro de TVA", max_length=50, blank=True)
    email = models.EmailField("Courriel", blank=True)
    reference = models.CharField("Référence client", max_length=100, blank=True)
    payment_days = models.PositiveSmallIntegerField("Délai de paiement (jours)", default=30,
        validators=[MaxValueValidator(3650)])
    payment_terms = models.CharField("Conditions de paiement", max_length=255, blank=True)
    invoice_format = models.CharField("Format de facturation", max_length=20,
        choices=InvoiceFormat.choices, blank=True, default="")
    peppol_endpoint_id = models.CharField("Identifiant électronique Peppol", max_length=100, blank=True)
    peppol_endpoint_scheme = models.CharField("Schéma Peppol (EAS)", max_length=4, blank=True)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "client"
        verbose_name_plural = "clients"
        default_permissions = ("add", "change", "view")
        permissions = [("configure_customer_billing", "Modifier les paramètres de facturation des clients")]

    def __str__(self):
        return f"{self.code} — {self.name}"


class IssuerConfiguration(models.Model):
    name = models.CharField("Raison sociale", max_length=255)
    street = models.CharField("Rue et numéro", max_length=255)
    zip_code = models.CharField("Code postal", max_length=20)
    city = models.CharField("Ville", max_length=100)
    country = models.CharField("Pays (ISO)", max_length=2, default="BE", validators=[country_code])
    vat_number = models.CharField("Numéro de TVA", max_length=50, blank=True)
    legal_id = models.CharField("Identifiant légal / BCE", max_length=50)
    email = models.EmailField("Courriel", blank=True)
    iban = models.CharField("IBAN", max_length=34)
    peppol_endpoint_id = models.CharField("Identifiant électronique Peppol", max_length=100, blank=True)
    peppol_endpoint_scheme = models.CharField("Schéma Peppol (EAS)", max_length=4, blank=True)

    class Meta:
        verbose_name = "paramètres de l’émetteur"
        verbose_name_plural = "paramètres de l’émetteur"
        default_permissions = ("view", "change")
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="sales_single_issuer")]

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self.iban = self.iban.replace(" ", "").upper()
        if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", self.iban):
            raise ValidationError({"iban": "Renseignez un IBAN valide."})
        rearranged = self.iban[4:] + self.iban[:4]
        digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in rearranged)
        if int(digits) % 97 != 1:
            raise ValidationError({"iban": "La clé de contrôle de l’IBAN est invalide."})


class TrainingService(models.Model):
    code = models.CharField("Code", max_length=50, unique=True)
    description = models.CharField("Formation / service", max_length=255)
    unit = models.CharField("Unité (UNECE)", max_length=3, default="C62")
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "formation"
        verbose_name_plural = "formations"
        default_permissions = ("add", "change", "view")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.description}"


class SalesSequence(models.Model):
    series = models.CharField(max_length=2, choices=[("CV", "Commande"), ("FV", "Facture")])
    year = models.PositiveIntegerField()
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["series", "year"], name="sales_unique_series_year")]


class SalesOrder(models.Model):
    objects = ProtectedQuerySet.as_manager()
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        CONFIRMED = "CONFIRMED", "Confirmée"
        INVOICED = "INVOICED", "Facturée"
        CANCELLED = "CANCELLED", "Annulée"

    number = models.CharField("Numéro", max_length=30, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, verbose_name="Client")
    order_date = models.DateField("Date", default=timezone.localdate)
    customer_reference = models.CharField("Référence de commande du client", max_length=100, blank=True)
    currency = models.CharField("Devise", max_length=3, default="EUR", choices=[("EUR", "EUR")])
    status = models.CharField("Statut", max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField("Notes internes", blank=True)
    subtotal = models.DecimalField("Total HT", max_digits=18, decimal_places=2, default=0)
    tax_total = models.DecimalField("TVA", max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField("Total TTC", max_digits=18, decimal_places=2, default=0)
    revision = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "commande de vente"
        verbose_name_plural = "commandes de vente"
        default_permissions = ("view", "add", "change")
        permissions = [("confirm_salesorder", "Confirmer les commandes de vente"),
                       ("cancel_salesorder", "Annuler les commandes de vente")]

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding:
                old = type(self).objects.select_for_update().get(pk=self.pk)
                frozen = ("number", "customer_id", "order_date", "customer_reference", "currency",
                    "notes", "subtotal", "tax_total", "total")
                if old.status != "DRAFT" and any(getattr(old, f) != getattr(self, f) for f in frozen):
                    raise ValidationError("Les données d’une commande confirmée sont protégées.")
                transitions = {"DRAFT": {"CONFIRMED", "CANCELLED"}, "CONFIRMED": {"INVOICED", "CANCELLED"}}
                if old.status != self.status and self.status not in transitions.get(old.status, set()):
                    raise ValidationError("Transition de commande non autorisée.")
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Annulez la commande pour conserver son historique.")


class CommercialLine(models.Model):
    description = models.CharField("Description", max_length=255)
    quantity = models.DecimalField("Quantité", max_digits=12, decimal_places=4,
        validators=[MinValueValidator(Decimal("0.0001"))], default=1)
    unit = models.CharField("Unité (UNECE)", max_length=3, default="C62")
    unit_price = models.DecimalField("Prix unitaire HT", max_digits=14, decimal_places=4,
        validators=[MinValueValidator(0)])
    discount = models.DecimalField("Remise HT (montant)", max_digits=14, decimal_places=2,
        default=0, validators=[MinValueValidator(0)])
    tax_code = models.CharField("Catégorie TVA", max_length=2,
        choices=[("S", "S — TVA standard"), ("Z", "Z — Taux zéro"),
                 ("E", "E — Exonération"), ("AE", "AE — Autoliquidation"),
                 ("O", "O — Hors champ")])
    tax_rate = models.DecimalField("Taux TVA (%)", max_digits=7, decimal_places=4,
        validators=[MinValueValidator(0), MaxValueValidator(100)])
    exemption_reason = models.CharField("Motif d’exonération / autoliquidation", max_length=255, blank=True)
    service_start = models.DateField("Début de prestation", null=True, blank=True)
    service_end = models.DateField("Fin de prestation", null=True, blank=True)
    cost_center = models.ForeignKey("budgeting.CostCenter", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="CDF")
    funding = models.ForeignKey("budgeting.Funding", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Financement")
    budget_product = models.ForeignKey("budgeting.BudgetProduct", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Produit budgétaire")
    support = models.ForeignKey("budgeting.Support", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Support")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    tax_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)
    total = models.DecimalField(max_digits=18, decimal_places=2, default=0, editable=False)

    class Meta:
        abstract = True
        ordering = ["pk"]

    def clean(self):
        super().clean()
        if self.quantity is not None and self.unit_price is not None and self.discount is not None:
            if self.discount > rounded(self.quantity * self.unit_price):
                raise ValidationError({"discount": "La remise dépasse le montant de la ligne."})
        if self.tax_rate is not None:
            if self.tax_code == "S" and self.tax_rate <= 0:
                raise ValidationError({"tax_rate": "Le taux standard doit être strictement positif."})
            if self.tax_code in ("Z", "E", "AE", "O") and self.tax_rate != 0:
                raise ValidationError({"tax_rate": "Cette catégorie exige un taux nul."})
        if self.tax_code in ("E", "AE", "O") and not self.exemption_reason.strip():
            raise ValidationError({"exemption_reason": "Renseignez le motif fiscal."})
        if self.service_start and self.service_end and self.service_end < self.service_start:
            raise ValidationError({"service_end": "La fin précède le début de prestation."})
        if bool(self.service_start) != bool(self.service_end):
            raise ValidationError("Renseignez les deux dates de prestation ou aucune.")

    def calculate(self):
        self.subtotal = rounded(self.quantity * self.unit_price - self.discount)
        self.tax_amount = rounded(self.subtotal * self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount


class SalesOrderLine(CommercialLine):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="lines")
    service = models.ForeignKey(TrainingService, on_delete=models.PROTECT, null=True, blank=True,
        verbose_name="Formation (facultative)")

    class Meta(CommercialLine.Meta):
        default_permissions = ()
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="sales_order_positive_qty"),
            models.CheckConstraint(condition=models.Q(unit_price__gte=0, discount__gte=0), name="sales_order_positive_prices"),
            models.CheckConstraint(condition=models.Q(tax_rate__gte=0, tax_rate__lte=100), name="sales_order_tax_range"),
        ]

    def save(self, *args, **kwargs):
        with transaction.atomic():
            parent = SalesOrder.objects.select_for_update().get(pk=self.order_id)
            if parent.status != SalesOrder.Status.DRAFT:
                raise ValidationError("Seules les lignes d’un brouillon sont modifiables.")
            if self.pk and type(self).objects.filter(pk=self.pk).exclude(order_id=self.order_id).exists():
                raise ValidationError("Une ligne ne peut pas changer de commande.")
            self.full_clean()
            self.calculate()
            self.full_clean()
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            parent = SalesOrder.objects.select_for_update().get(pk=self.order_id)
            if parent.status != SalesOrder.Status.DRAFT:
                raise ValidationError("Cette commande est protégée.")
            return super().delete(*args, **kwargs)


class SalesInvoice(models.Model):
    objects = ProtectedQuerySet.as_manager()
    class DocumentStatus(models.TextChoices):
        DRAFT = "DRAFT", "En préparation"
        ISSUED = "ISSUED", "Émise — document disponible"
        ERROR = "DOCUMENT_ERROR", "Émise — erreur documentaire"
        CANCELLED = "CANCELLED_BEFORE_ISSUE", "Annulée avant émission"

    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Non payée"
        PARTIAL = "PARTIALLY_PAID", "Partiellement payée"
        PAID = "PAID", "Payée"

    order = models.OneToOneField(SalesOrder, on_delete=models.PROTECT, related_name="invoice")
    number = models.CharField("Numéro", max_length=30, unique=True)
    issue_date = models.DateField("Date d’émission")
    due_date = models.DateField("Échéance")
    currency = models.CharField(max_length=3)
    invoice_format = models.CharField("Format", max_length=20, choices=InvoiceFormat.choices)
    document_status = models.CharField("État documentaire", max_length=24,
        choices=DocumentStatus.choices, default=DocumentStatus.ERROR)
    payment_status = models.CharField("Paiement", max_length=16,
        choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    subtotal = models.DecimalField("Total HT", max_digits=18, decimal_places=2)
    tax_total = models.DecimalField("TVA", max_digits=18, decimal_places=2)
    total = models.DecimalField("Total TTC", max_digits=18, decimal_places=2)
    customer_snapshot = models.JSONField()
    issuer_snapshot = models.JSONField()
    order_snapshot = models.JSONField()
    tax_breakdown = models.JSONField()
    document_error = models.TextField(blank=True)
    issued_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date", "-pk"]
        verbose_name = "facture de vente"
        verbose_name_plural = "factures de vente"
        default_permissions = ("view",)
        permissions = [("issue_salesinvoice", "Émettre les factures de vente"),
                       ("download_salesinvoice", "Télécharger les factures de vente"),
                       ("regenerate_salesinvoice", "Régénérer et valider les documents de vente"),
                       ("record_invoicepayment", "Enregistrer et corriger les paiements de vente"),
                       ("view_salesreport", "Consulter le suivi des ventes par dimension budgétaire")]

    COMMERCIAL_FIELDS = ("order_id", "number", "issue_date", "due_date", "currency", "invoice_format",
        "subtotal", "tax_total", "total", "customer_snapshot", "issuer_snapshot", "order_snapshot",
        "tax_breakdown", "issued_at")

    sealed = models.BooleanField(default=False, editable=False)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding:
                old = type(self).objects.select_for_update().get(pk=self.pk)
                if any(getattr(old, f) != getattr(self, f) for f in self.COMMERCIAL_FIELDS) or (old.sealed and not self.sealed):
                    raise ValidationError("Les données d’une facture émise sont immuables.")
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Une facture émise ne peut pas être supprimée.")

    def __str__(self):
        return self.number


class SalesInvoiceLine(CommercialLine, AppendOnlyModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="lines")
    position = models.PositiveIntegerField()
    dimension_snapshot = models.JSONField(default=dict)

    class Meta(CommercialLine.Meta):
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["invoice", "position"], name="sales_unique_invoice_position")]

    def save(self, *args, **kwargs):
        raise ValidationError("Les lignes de facture sont créées uniquement lors de l’émission.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Une ligne de facture est immuable.")


class InvoiceDocument(AppendOnlyModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="documents")
    document_type = models.CharField(max_length=20, choices=InvoiceFormat.choices)
    storage_path = models.CharField(max_length=500)
    checksum = models.CharField(max_length=64)
    generator_version = models.CharField(max_length=50, default="sales-v1")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["-pk"]


class InvoiceValidationRun(AppendOnlyModel):
    document = models.ForeignKey(InvoiceDocument, on_delete=models.PROTECT, related_name="validations")
    status = models.CharField(max_length=12, choices=[("VALID", "Conforme"), ("INVALID", "Non conforme"),
        ("UNAVAILABLE", "Validation indisponible"), ("NOT_REQUIRED", "Sans objet — PDF")])
    details = models.JSONField(default=list)
    rules_version = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["-pk"]


class InvoicePayment(AppendOnlyModel):
    invoice = models.ForeignKey(SalesInvoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField("Montant reçu", max_digits=18, decimal_places=2,
        validators=[MinValueValidator(MONEY)])
    payment_date = models.DateField("Date de paiement", default=timezone.localdate)
    reference = models.CharField("Référence / justification", max_length=255)
    token = models.UUIDField(unique=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["-payment_date", "-pk"]
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="sales_payment_positive")]


class PaymentReversal(AppendOnlyModel):
    payment = models.OneToOneField(InvoicePayment, on_delete=models.PROTECT, related_name="reversal")
    reason = models.CharField("Motif de correction", max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()


class SalesEvent(AppendOnlyModel):
    order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="events")
    invoice = models.ForeignKey(SalesInvoice, null=True, on_delete=models.PROTECT, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["-pk"]
