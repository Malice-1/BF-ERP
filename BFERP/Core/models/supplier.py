from django.db import models

class Supplier(models.Model):
    name=models.CharField(max_length=150)
    address=models.TextField()
    email=models.EmailField()
    phone_number=models.CharField(max_length=12)

