from django.apps import AppConfig


class AccountsConfig(AppConfig):
    verbose_name = "Comptes et accès"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in
        from django.db.models.signals import post_migrate
        from .permission_labels import localize_permissions
        from .sessions import register_active_login

        user_logged_in.connect(register_active_login, dispatch_uid="accounts.active_login")
        post_migrate.connect(localize_permissions, dispatch_uid="accounts.french_permissions")

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'
