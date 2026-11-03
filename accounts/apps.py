from django.apps import AppConfig


class AccountsConfig(AppConfig):
    verbose_name = "Comptes et accès"

    def ready(self):
        from django.db.models.signals import post_migrate
        from .permission_labels import localize_permissions
        post_migrate.connect(localize_permissions, dispatch_uid="accounts.french_permissions")

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
