from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Employee(models.Model):
    number = models.CharField("Matricule", max_length=50, unique=True)
    first_name = models.CharField("Prénom", max_length=100)
    last_name = models.CharField("Nom", max_length=100)
    work_email = models.EmailField("Adresse e-mail professionnelle", blank=True)
    work_phone = models.CharField("Téléphone professionnel", max_length=40, blank=True)
    job_title = models.CharField("Fonction", max_length=150, blank=True)
    department = models.CharField("Service", max_length=150, blank=True)
    start_date = models.DateField("Date d’entrée", null=True, blank=True)
    end_date = models.DateField("Date de sortie", null=True, blank=True)
    is_active = models.BooleanField("Actif", default=True)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ("last_name", "first_name", "number")
        verbose_name = "employé"
        verbose_name_plural = "employés"
        default_permissions = ("view", "add", "change")
        constraints = [models.CheckConstraint(
            condition=models.Q(start_date__isnull=True) | models.Q(end_date__isnull=True)
            | models.Q(end_date__gte=models.F("start_date")), name="hr_employment_dates",
        )]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class PayrollDetails(models.Model):
    class Frequency(models.TextChoices):
        MONTHLY = "MONTHLY", "Mensuelle"
        HOURLY = "HOURLY", "Horaire"
        ANNUAL = "ANNUAL", "Annuelle"

    employee = models.OneToOneField(Employee, on_delete=models.PROTECT, related_name="payroll")
    gross_amount = models.DecimalField("Rémunération brute de base (EUR)", max_digits=14, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))], blank=True, null=True)
    frequency = models.CharField("Base de rémunération", max_length=10, choices=Frequency.choices,
                                 default=Frequency.MONTHLY)
    work_percentage = models.DecimalField("Temps de travail (%)", max_digits=5, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(Decimal("100"))], blank=True, null=True)
    effective_date = models.DateField("Date d’effet", blank=True, null=True)
    iban = models.CharField("IBAN de versement", max_length=34, blank=True)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        verbose_name = "données de paie"
        verbose_name_plural = "données de paie"
        default_permissions = ("view", "change")
