from django.db import models

class Warehouse(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Code")
    label = models.CharField(max_length=150, verbose_name="Dépôt")

    class Meta:
        verbose_name = "dépôt"
        verbose_name_plural = "dépôts"

    def __str__(self):
        return f"{self.code} — {self.label}"


class StockBalance(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT)
    product = models.ForeignKey("purchasing.DetailedProduct", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = "stock"
        verbose_name_plural = "stocks"
        default_permissions = ("view",)
        permissions = [("manage_stock", "Enregistrer les mouvements et inventaires de stock")]
        constraints = [models.UniqueConstraint(fields=["warehouse", "product"], name="unique_stock_balance"),
                       models.CheckConstraint(condition=models.Q(quantity__gte=0), name="nonnegative_stock")]


class StockMovement(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, related_name="movements")
    destination = models.ForeignKey(Warehouse, null=True, blank=True, on_delete=models.PROTECT, related_name="incoming_movements")
    product = models.ForeignKey("purchasing.DetailedProduct", on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=[("receipt", "Entrée"), ("issue", "Sortie"), ("transfer", "Transfert"), ("inventory", "Inventaire")])
    quantity = models.DecimalField(max_digits=18, decimal_places=4)
    delta = models.DecimalField(max_digits=18, decimal_places=4)
    reason = models.TextField()
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    token = models.UUIDField(unique=True, editable=False)

    class Meta:
        default_permissions = ("view",)
        ordering = ["-pk"]
        verbose_name = "mouvement de stock"
        verbose_name_plural = "mouvements de stock"

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if not self._state.adding:
            raise ValidationError("Un mouvement de stock est immuable. Enregistrez une correction distincte.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Un mouvement de stock ne peut pas être supprimé.")


class PurchaseReceipt(models.Model):
    order = models.ForeignKey("purchasing.PurchaseOrder", on_delete=models.PROTECT, related_name="receipts", verbose_name="Bon de commande")
    warehouse = models.ForeignKey(Warehouse, on_delete=models.PROTECT, verbose_name="Dépôt de réception")
    actor = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, verbose_name="Réceptionné par")
    reason = models.TextField(verbose_name="Référence du bon de livraison / commentaire")
    token = models.UUIDField(unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        default_permissions = ()
        ordering = ["-pk"]
        verbose_name = "réception de demande d’achat"
        verbose_name_plural = "réceptions de demandes d’achat"

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if not self._state.adding:
            raise ValidationError("Une réception enregistrée est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Une réception enregistrée ne peut pas être supprimée.")


class PurchaseReceiptLine(models.Model):
    receipt = models.ForeignKey(PurchaseReceipt, on_delete=models.PROTECT, related_name="lines")
    purchase_line = models.ForeignKey("purchasing.PurchaseRequestLine", on_delete=models.PROTECT, related_name="receipt_lines")
    movement = models.OneToOneField(StockMovement, on_delete=models.PROTECT, related_name="receipt_line")

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["receipt", "purchase_line"], name="unique_purchase_receipt_line")]

    def save(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        if not self._state.adding:
            raise ValidationError("Une ligne de réception enregistrée est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Une ligne de réception enregistrée ne peut pas être supprimée.")
