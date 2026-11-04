"""Procurement snapshots and budget ledger, independent of legacy budget counters."""
from django.conf import settings
from django.db import models
from django.db.models import Q
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction


class PublishedVersion(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self._state.adding and type(self).objects.select_for_update().get(pk=self.pk).published_at:
                raise ValidationError("Une version publiée est immuable.")
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.published_at:
            raise ValidationError("Une version publiée est immuable.")
        return super().delete(*args, **kwargs)


class VersionChild(models.Model):
    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        with transaction.atomic():
            parent = self._meta.get_field("version").remote_field.model
            if parent.objects.select_for_update().get(pk=self.version_id).published_at:
                raise ValidationError("Une version publiée est immuable. Copiez-la en brouillon.")
            if self.pk is not None and not self._state.adding:
                old_version = type(self).objects.get(pk=self.pk).version_id
                if old_version != self.version_id:
                    raise ValidationError("Une ligne ne peut pas changer de version.")
            return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            parent = self._meta.get_field("version").remote_field.model
            if parent.objects.select_for_update().get(pk=self.version_id).published_at:
                raise ValidationError("Une version publiée est immuable.")
            return super().delete(*args, **kwargs)


def order_number():
    return "BC-" + uuid4().hex[:20].upper()


class AnnualEnvelope(models.Model):
    year = models.PositiveIntegerField(unique=True, verbose_name='Année')
    active_version = models.ForeignKey("EnvelopeVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+", verbose_name='Version active')

    class Meta:
        verbose_name = "Enveloppe budgétaire annuelle"
        default_permissions = ()
        verbose_name_plural = "Enveloppes budgétaires annuelles"

    def __str__(self):
        return str(self.year)


class EnvelopeVersion(PublishedVersion):
    envelope = models.ForeignKey(AnnualEnvelope, on_delete=models.PROTECT, related_name="versions", verbose_name='Enveloppe annuelle')
    label = models.CharField(max_length=100, verbose_name='Libellé')
    published_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name='Date de publication')

    class Meta:
        verbose_name = "Version budgétaire achats"
        default_permissions = ()
        verbose_name_plural = "Versions budgétaires achats"

    def __str__(self):
        return f"{self.envelope} · {self.label}"


class Allocation(VersionChild):
    version = models.ForeignKey(EnvelopeVersion, on_delete=models.PROTECT, related_name="allocations", verbose_name='Version')
    cost_center = models.ForeignKey("budgeting.CostCenter", on_delete=models.PROTECT, verbose_name='CDF')
    funding = models.ForeignKey("budgeting.Funding", on_delete=models.PROTECT, verbose_name='Financement')
    budget_product = models.ForeignKey("budgeting.BudgetProduct", on_delete=models.PROTECT, verbose_name='Produit budgétaire (BI)')
    amount = models.DecimalField(max_digits=28, decimal_places=10, verbose_name='Montant TVAC')

    class Meta:
        verbose_name = "Allocation TVAC"
        default_permissions = ()
        verbose_name_plural = "Allocations TVAC"
        constraints = [models.UniqueConstraint(fields=["version", "cost_center", "funding", "budget_product"], name="procurement_unique_allocation"), models.CheckConstraint(condition=Q(amount__gte=0), name="procurement_positive_allocation")]


class WorkflowVersion(PublishedVersion):
    operation = models.CharField(max_length=40, default="purchase", verbose_name="Type d’opération")
    rule_based = models.BooleanField(default=False, verbose_name="Éditeur de règles conditionnelles")
    label = models.CharField(max_length=100, verbose_name='Libellé')
    active = models.BooleanField(default=False, editable=False, verbose_name='Active')
    published_at = models.DateTimeField(null=True, blank=True, editable=False, verbose_name='Date de publication')

    class Meta:
        verbose_name = "Configuration des validations"
        verbose_name_plural = "Configurations des validations"
        constraints = [models.UniqueConstraint(fields=["operation"], condition=Q(active=True), name="procurement_one_workflow")]
        permissions = [("monitor_purchases", "Consulter le suivi opérationnel des achats"), ("reassign_approvals", "Réaffecter les étapes d'achat"), ("view_purchase_financial", "Consulter les données financières des achats")]

    def __str__(self):
        return self.label


class ApprovalRule(VersionChild):
    conditions = models.JSONField(default=dict, blank=True, verbose_name="Conditions")
    named_user_reference = models.CharField(max_length=220, blank=True, editable=False,
                                           verbose_name="Valideur nommé mémorisé")

    def save(self, *args, **kwargs):
        if self.named_user_reference.startswith("[référence supprimée:"):
            return super().save(*args, **kwargs)
        if self.named_user_id:
            self.named_user_reference = f"{self.named_user_id}: {self.named_user.username}"
        elif self.cdf_manager or self.support_manager or self.role_id:
            self.named_user_reference = ""
        return super().save(*args, **kwargs)

    role = models.ForeignKey("accounts.Role", null=True, blank=True, on_delete=models.PROTECT,
        verbose_name="Rôle valideur")
    version = models.ForeignKey(WorkflowVersion, on_delete=models.PROTECT, related_name="rules", verbose_name='Version')
    label = models.CharField(max_length=100, verbose_name='Libellé')
    function = models.ForeignKey("accounts.ValidationFunction", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Fonction de validation')
    level = models.PositiveIntegerField(default=1, verbose_name='Niveau')
    mode = models.CharField(max_length=12, choices=[("cumulative", "Cumulative"), ("exclusive", "Exclusive")], default="cumulative", verbose_name='Mode de règle')
    priority = models.IntegerField(default=0, verbose_name='Priorité')
    minimum_htva = models.DecimalField(max_digits=24, decimal_places=4, default=0, verbose_name='Total DA HTVA minimum inclus')
    maximum_htva = models.DecimalField(max_digits=24, decimal_places=4, null=True, blank=True, verbose_name='Total DA HTVA maximum exclu')
    cost_center = models.ForeignKey("budgeting.CostCenter", null=True, blank=True, on_delete=models.PROTECT, verbose_name='CDF')
    funding = models.ForeignKey("budgeting.Funding", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Financement')
    budget_product = models.ForeignKey("budgeting.BudgetProduct", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Produit budgétaire (BI)')
    named_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Valideur nommé')
    cdf_manager = models.BooleanField(default=False, verbose_name='Affecter aux responsables CDF')
    support_manager = models.BooleanField(default=False, verbose_name="Affecter aux responsables du support")

    class Meta:
        verbose_name = "Règle de validation"
        verbose_name_plural = "Règles de validation"
        ordering = ["level", "pk"]


class Submission(models.Model):
    purchase_request = models.ForeignKey("PurchaseRequest", on_delete=models.PROTECT, related_name="submissions", verbose_name='Demande d’achat')
    workflow = models.ForeignKey(WorkflowVersion, on_delete=models.PROTECT, verbose_name='Circuit de validation')
    budget_version = models.ForeignKey(EnvelopeVersion, on_delete=models.PROTECT, verbose_name='Version budgétaire')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    active = models.BooleanField(default=True, verbose_name='Active')
    supplier_data = models.JSONField(default=dict, verbose_name='Données figées du fournisseur')

    class Meta:
        verbose_name = 'cycle de soumission'
        verbose_name_plural = 'cycles de soumission'
        constraints = [models.UniqueConstraint(fields=["purchase_request"], condition=Q(active=True), name="procurement_one_submission")]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class LineSnapshot(models.Model):
    support = models.ForeignKey("budgeting.Support", null=True, blank=True,
        on_delete=models.PROTECT, verbose_name="Support demandeur")
    submission = models.ForeignKey(Submission, on_delete=models.PROTECT, related_name="lines", verbose_name='Cycle de soumission')
    line = models.ForeignKey("PurchaseRequestLine", on_delete=models.SET_NULL, null=True, verbose_name='Ligne de demande')
    original_line_id = models.PositiveBigIntegerField(verbose_name='Identifiant de la ligne d’origine')
    data = models.JSONField(verbose_name='Données figées')
    amount = models.DecimalField(max_digits=28, decimal_places=10, verbose_name='Montant TVAC')
    cost_center = models.ForeignKey("budgeting.CostCenter", on_delete=models.PROTECT, verbose_name='CDF')
    funding = models.ForeignKey("budgeting.Funding", on_delete=models.PROTECT, verbose_name='Financement')
    budget_product = models.ForeignKey("budgeting.BudgetProduct", on_delete=models.PROTECT, verbose_name='Produit budgétaire (BI)')

    class Meta:
        verbose_name = 'instantané de ligne'
        verbose_name_plural = 'instantanés de ligne'

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class BudgetEntry(models.Model):
    def __str__(self):
        return f"Écriture budgétaire n° {self.pk}"

    snapshot = models.OneToOneField(LineSnapshot, on_delete=models.PROTECT, related_name="entry", verbose_name='Instantané de ligne')
    state = models.CharField(max_length=12, choices=[("reserved", "Réservé"), ("committed", "Engagé"), ("released", "Libéré")], default="reserved", verbose_name='État')
    amount = models.DecimalField(max_digits=28, decimal_places=10, verbose_name='Montant TVAC')

    class Meta:
        default_permissions = ()


class ApprovalStep(models.Model):
    rule_snapshot = models.JSONField(default=dict, blank=True, verbose_name="Règle et conditions appliquées")
    manager_source = models.CharField(max_length=10, blank=True, choices=[("cdf", "CDF"), ("support", "Support")], verbose_name='Origine des responsables')
    role = models.ForeignKey("accounts.Role", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Rôle')
    snapshot = models.ForeignKey(LineSnapshot, on_delete=models.PROTECT, related_name="steps", verbose_name='Instantané de ligne')
    function = models.ForeignKey("accounts.ValidationFunction", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Fonction de validation')
    function_label = models.CharField(max_length=100, verbose_name='Libellé de la fonction')
    level = models.PositiveIntegerField(verbose_name='Niveau')
    candidates = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="purchase_steps", verbose_name='Valideurs affectés')
    state = models.CharField(max_length=16, default="future", choices=[("future", "Non accessible"), ("pending", "En attente"), ("unassigned", "À affecter"), ("blocked", "Habilitation bloquée"), ("approved", "Approuvée"), ("stopped", "Arrêtée")], verbose_name='État')
    waiting_since = models.DateTimeField(null=True, blank=True, verbose_name='En attente depuis')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_approvals", verbose_name='Approuvé par')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='Date d’approbation')
    authorization = models.ForeignKey("accounts.AuthorizationVersion", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Habilitation')
    evidence = models.ForeignKey("ApprovalStep", null=True, blank=True, on_delete=models.PROTECT, verbose_name='Preuve de validation')
    evaluated_scope = models.JSONField(default=dict, verbose_name='Périmètre évalué')

    class Meta:
        verbose_name = 'étape de validation'
        verbose_name_plural = 'étapes de validation'
        ordering = ["snapshot_id", "level", "pk"]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class PurchaseOrder(models.Model):
    purchase_request = models.OneToOneField("PurchaseRequest", on_delete=models.PROTECT, related_name="order", verbose_name='Demande d’achat')
    submission = models.OneToOneField(Submission, on_delete=models.PROTECT, verbose_name='Cycle de soumission')
    number = models.CharField(max_length=30, unique=True, default=order_number, verbose_name='Numéro')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    supplier_data = models.JSONField(verbose_name='Données figées du fournisseur')

    def __str__(self):
        return self.number

    class Meta:
        verbose_name = 'bon de commande'
        verbose_name_plural = 'bons de commande'


class Delegation(models.Model):
    principal = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_delegations", verbose_name='Titulaire')
    delegate = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="delegated_purchases", verbose_name='Remplaçant')
    valid_from = models.DateTimeField(verbose_name='Début de validité')
    valid_until = models.DateTimeField(verbose_name='Fin de validité')

    class Meta:
        verbose_name = 'délégation'
        verbose_name_plural = 'délégations'
        constraints = [models.CheckConstraint(condition=Q(valid_until__gt=models.F("valid_from")), name="procurement_delegation_dates"), models.CheckConstraint(condition=~Q(principal=models.F("delegate")), name="procurement_delegation_distinct")]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class PurchaseNotice(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Destinataire')
    step = models.ForeignKey(ApprovalStep, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Étape de validation')
    key = models.CharField(max_length=160, unique=True, verbose_name='Clé de déduplication')
    message = models.CharField(max_length=255, verbose_name='Message')
    active = models.BooleanField(default=True, verbose_name='Active')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    email_state = models.CharField(max_length=16, default="pending", verbose_name='État d’envoi du courriel',
        choices=[("pending", "En attente"), ("sent", "Envoyé"), ("failed", "Échec temporaire"),
                 ("permanent", "Échec permanent"), ("obsolete", "Obsolète")])
    attempts = models.PositiveIntegerField(default=0, verbose_name='Nombre de tentatives')
    retry_at = models.DateTimeField(null=True, blank=True, verbose_name='Prochaine tentative')

    class Meta:
        verbose_name = 'notification de validation'
        verbose_name_plural = 'notifications de validation'

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"
