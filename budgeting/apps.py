from django.apps import AppConfig


class BudgetingConfig(AppConfig):
    verbose_name = "Budgets"
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'budgeting'

    def ready(self):
        from .history import connect
        connect()
