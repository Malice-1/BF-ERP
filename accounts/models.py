from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator


class SessionPolicy(models.Model):
    idle_timeout_minutes = models.PositiveIntegerField(
        default=120, validators=[MinValueValidator(1), MaxValueValidator(10080)],
        verbose_name="Déconnexion après inactivité (minutes)",
    )

    class Meta:
        verbose_name = 'politique de déconnexion'
        verbose_name_plural = 'politiques de déconnexion'
        constraints = [models.CheckConstraint(
            condition=models.Q(idle_timeout_minutes__gte=1, idle_timeout_minutes__lte=10080),
            name="session_timeout_valid_range",
        )]

    @classmethod
    def timeout_seconds(cls):
        minutes = cls.objects.filter(pk=1).values_list("idle_timeout_minutes", flat=True).first()
        return (minutes if minutes is not None else 120) * 60

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class Role(models.Model):
    permissions = models.ManyToManyField(
        "auth.Permission", blank=True, verbose_name="Permissions",
        help_text="Droits hérités par les utilisateurs auxquels ce rôle est attribué.",
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name='Code',
    )

    label = models.CharField(
        max_length=100,
        verbose_name='Libellé',
    )

    def __str__(self):
        return self.label

    class Meta:
        verbose_name = 'rôle ERP'
        verbose_name_plural = 'rôles ERP'


class User(AbstractUser):
    supports = models.ManyToManyField("budgeting.Support", blank=True,
        related_name="members", verbose_name="Supports d’appartenance",
        help_text="Supports auxquels appartient l’utilisateur. Cette appartenance ne donne pas le rôle de responsable.")
    roles = models.ManyToManyField(
        Role,
        blank=True,
        verbose_name='Rôles ERP',
    )

    def __str__(self):
        return self.username

    class Meta:
        verbose_name = 'utilisateur'
        verbose_name_plural = 'utilisateurs'


class ActiveLogin(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    token = models.CharField(max_length=32, editable=False)

    class Meta:
        default_permissions = ()


class ValidationFunction(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name='Code')
    label = models.CharField(max_length=100, verbose_name='Libellé')
    position = models.PositiveIntegerField(unique=True, verbose_name='Position')

    class Meta:
        verbose_name = 'fonction de validation'
        verbose_name_plural = 'fonctions de validation'
        ordering = ["position", "pk"]

    def __str__(self):
        return self.label


class Authorization(models.Model):
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="authorizations", verbose_name='Utilisateur')
    function = models.ForeignKey(ValidationFunction, on_delete=models.PROTECT, verbose_name='Fonction de validation')
    current_version = models.ForeignKey(
        "AuthorizationVersion", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
        verbose_name='Version courante',
    )

    class Meta:
        verbose_name = 'habilitation'
        verbose_name_plural = 'habilitations'
        permissions = [("manage_authorizations", "Gérer les habilitations versionnées")]

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"


class AuthorizationVersion(models.Model):
    authorization = models.ForeignKey(Authorization, on_delete=models.PROTECT, related_name="versions", verbose_name='Habilitation')
    version = models.PositiveIntegerField(verbose_name='Version')
    valid_from = models.DateTimeField(verbose_name='Début de validité')
    valid_until = models.DateTimeField(null=True, blank=True, verbose_name='Fin de validité')
    scope = models.JSONField(default=dict, verbose_name='Périmètre')
    enabled = models.BooleanField(default=True, verbose_name='Activée')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Date de création')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Créé par')

    class Meta:
        verbose_name = 'version d’habilitation'
        verbose_name_plural = 'versions d’habilitation'
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

    def __str__(self):
        return f"{self._meta.verbose_name} n° {self.pk}"
