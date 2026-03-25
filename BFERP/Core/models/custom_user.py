from django.db import models
from django.contrib.auth.models import AbstractUser

class CustomUser(AbstractUser):
    avatar=models.ImageField(upload_to="avatars/", null=True, blank=True)
    email=models.EmailField(unique=True)
    username=None

    USERNAME_FIELD='email'
    REQUIRED_FIELDS=[]

    def __str__(self):
        first=self.first_name or ""
        last=(self.last_name or "").upper()
        full_name=f"{first} {last}".strip()
        return full_name if full_name else self.email