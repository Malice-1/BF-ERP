from django.core.management.base import BaseCommand
from budgeting.history import initialize


class Command(BaseCommand):
    help = "Enregistre un état initial des enveloppes sans historique, sans inventer d’états passés."

    def handle(self, *args, **options):
        count = initialize()
        self.stdout.write(self.style.SUCCESS(f"{count} enveloppe(s) initialisée(s)."))
