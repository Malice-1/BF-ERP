from django.urls import path
from . import views
from . import flow_views
from . import budget_views

app_name = "purchasing"
urlpatterns = [
    path("toutes-les-demandes/", views.all_requests, name="all_requests"),
    path("produits-detailles/", budget_views.detailed_products, name="detailed_products"),
    path("espace-budget/", budget_views.budget_home, name="budget_home"),
    path("alimentation-budgets/", budget_views.allocation_versions, name="allocation_versions"),
    path("configuration/", budget_views.configuration, name="configuration"),
    path("produits-budgetaires/", budget_views.budget_products, name="budget_products"),
    path("gestion-budgets/", budget_views.versions, name="budget_versions"),
    path("gestion-budgets/<int:pk>/", budget_views.version_detail, name="budget_version"),
    path("verifier-budget/", flow_views.budget_check, name="budget_check"),
    path("validations/", flow_views.inbox, name="inbox"),
    path("suivi/", flow_views.monitor, name="monitor"),
    path("budgets/", flow_views.budgets, name="budgets"),
    path("delegations/", flow_views.delegations, name="delegations"),
    path("<int:pk>/soumettre/", flow_views.submit, name="submit"),
    path("<int:pk>/etapes/<int:step_id>/decision/", flow_views.decision, name="decision"),
    path("<int:pk>/etapes/<int:step_id>/reaffecter/", flow_views.reassign, name="reassign"),
    path("<int:pk>/commande/", flow_views.order_document, name="order"),
    path("", views.request_list, name="list"),
    path("nouvelle/", views.request_create, name="create"),
    path("<int:pk>/", views.request_detail, name="detail"),
    path("<int:pk>/modifier/", views.request_edit, name="edit"),
    path("<int:pk>/annuler/", views.request_cancel, name="cancel"),
    path("<int:pk>/lignes/ajouter/", views.line_edit, name="line_add"),
    path("<int:pk>/lignes/<int:line_id>/modifier/", views.line_edit, name="line_edit"),
    path("<int:pk>/lignes/<int:line_id>/supprimer/", views.line_delete, name="line_delete"),
]
