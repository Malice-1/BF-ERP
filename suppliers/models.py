from django.db import models


class Supplier(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    name = models.CharField(
        max_length=255
    )

    vat_number = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"



class SupplierContact(models.Model):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="contacts"
    )

    firstname = models.CharField(
        max_length=100,
        blank=True
    )

    lastname = models.CharField(
        max_length=100,
        blank=True
    )

    label = models.CharField(
        max_length=150
    )

    email = models.EmailField(
        blank=True
    )

    phone = models.CharField(
        max_length=50,
        blank=True
    )

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return self.label



class SupplierAddress(models.Model):
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="addresses"
    )

    label = models.CharField(
        max_length=100
    )

    street = models.CharField(
        max_length=255
    )

    city = models.CharField(
        max_length=100
    )

    zip_code = models.CharField(
        max_length=20
    )

    country = models.CharField(
        max_length=100
    )

    class Meta:
        ordering = ["label"]

    def __str__(self):
        return f"{self.label} - {self.city}"
