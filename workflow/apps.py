from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    verbose_name = "Historique et suivi"
    def ready(self):
        from .activity import connect
        connect()

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workflow'
