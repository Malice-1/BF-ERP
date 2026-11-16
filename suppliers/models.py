from django.db import models
from .identifiers import normalize_enterprise_number


class Supplier(models.Model):
    enterprise_number = models.CharField(
        'Numéro d’entreprise', max_length=50, blank=True, default="", db_index=True,
        help_text='Numéro du registre des entreprises. Pour une BCE belge, les points, espaces et le préfixe BE sont normalisés.',
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    name = models.CharField(
        max_length=255,
        verbose_name='Nom',
    )

    vat_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Numéro de TVA',
    )

    class Meta:
        verbose_name = 'fournisseur'
        verbose_name_plural = 'fournisseurs'
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean_fields(self, exclude=None):
        self.enterprise_number = normalize_enterprise_number(self.enterprise_number)
        return super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.enterprise_number = normalize_enterprise_number(self.enterprise_number)
        return super().save(*args, **kwargs)



class SupplierContact(models.Model):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="contacts",
        verbose_name='Fournisseur',
    )

    firstname = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Prénom',
    )

    lastname = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Nom',
    )

    label = models.CharField(
        max_length=150,
        verbose_name='Libellé',
    )

    email = models.EmailField(
        blank=True,
        verbose_name='Adresse de courriel',
    )

    phone = models.CharField(
        max_length=50,
        blank=True,
        verbose_name='Téléphone',
    )

    class Meta:
        verbose_name = 'contact fournisseur'
        verbose_name_plural = 'contacts fournisseurs'
        ordering = ["label"]

    def __str__(self):
        return self.label



class SupplierAddress(models.Model):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="addresses",
        verbose_name='Fournisseur',
    )

    label = models.CharField(
        max_length=100,
        verbose_name='Libellé',
    )

    street = models.CharField(
        max_length=255,
        verbose_name='Rue et numéro',
    )

    city = models.CharField(
        max_length=100,
        verbose_name='Ville',
    )

    zip_code = models.CharField(
        max_length=20,
        verbose_name='Code postal',
    )

    country = models.CharField(
        max_length=100,
        verbose_name='Pays',
    )

    class Meta:
        verbose_name = 'adresse fournisseur'
        verbose_name_plural = 'adresses fournisseurs'
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} - {self.city}"
