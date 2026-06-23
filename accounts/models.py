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
