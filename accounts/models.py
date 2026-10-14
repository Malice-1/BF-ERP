from django.db import models
from django.contrib.auth.models import AbstractUser


class Role(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True
    )

    label = models.CharField(
        max_length=100
    )

    def __str__(self):
        return self.label


class User(AbstractUser):
    roles = models.ManyToManyField(
        Role,
        blank=True
    )

    def __str__(self):
        return self.username


class ValidationFunction(models.Model):
    code = models.CharField(max_length=50, unique=True)
    label = models.CharField(max_length=100)
    position = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ["position", "pk"]

    def __str__(self):
        return self.label


class Authorization(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="authorizations")
    function = models.ForeignKey(ValidationFunction, on_delete=models.PROTECT)
    current_version = models.ForeignKey(
        "AuthorizationVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        permissions = [("manage_authorizations", "Gérer les habilitations versionnées")]


class AuthorizationVersion(models.Model):
    authorization = models.ForeignKey(Authorization, on_delete=models.PROTECT, related_name="versions")
    version = models.PositiveIntegerField()
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    scope = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["authorization", "version"], name="unique_authorization_version"),
            models.CheckConstraint(condition=models.Q(valid_until__isnull=True) | models.Q(valid_until__gt=models.F("valid_from")), name="authorization_valid_period"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            from django.core.exceptions import ValidationError
            raise ValidationError("Une version d'habilitation est immuable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError("Une version d'habilitation ne peut pas être supprimée.")
