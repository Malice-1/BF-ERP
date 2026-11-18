from django.urls import path
from . import views
from . import flow_views
from . import budget_views
from . import framework_views
from . import rule_views

from suppliers import views as supplier_views

app_name = "purchasing"
urlpatterns = [
    path("contrats-cadres/", framework_views.contract_list, name="framework_contracts"),
    path("contrats-cadres/nouveau/", framework_views.contract_edit, name="framework_contract_new"),
    path("contrats-cadres/<int:pk>/", framework_views.contract_detail, name="framework_contract_detail"),
    path("contrats-cadres/<int:pk>/modifier/", framework_views.contract_edit, name="framework_contract_edit"),
    path("fournisseurs/", supplier_views.supplier_list, name="suppliers"),
    path("fournisseurs/nouveau/", supplier_views.supplier_edit, name="supplier_create"),
    path("fournisseurs/<int:pk>/modifier/", supplier_views.supplier_edit, name="supplier_edit"),
    path("configuration/schemas-validation/", flow_views.validation_schemes, name="validation_schemes"),
    path("regles-validation/", rule_views.rule_sets, name="rule_sets"),
    path("regles-validation/<int:pk>/", rule_views.rule_set, name="rule_set"),
    path("regles-validation/<int:pk>/ajouter/", rule_views.rule_edit, name="rule_add"),
    path("regles-validation/<int:pk>/<int:rule_id>/modifier/", rule_views.rule_edit, name="rule_edit"),
    path("regles-validation/<int:pk>/<int:rule_id>/supprimer/", rule_views.rule_delete, name="rule_delete"),
    path("<int:pk>/simuler-validations/", rule_views.simulate, name="rule_simulate"),
    path("toutes-les-demandes/", views.all_requests, name="all_requests"),
    path("produits-detailles/", budget_views.detailed_products, name="detailed_products"),
    path("espace-budget/", budget_views.budget_home, name="budget_home"),
    path("alimentation-budgets/", budget_views.allocation_versions, name="allocation_versions"),
    path("historique-budgets/", budget_views.budget_history, name="budget_history"),
    path("historique-budgets/<int:version_id>/", budget_views.budget_history, name="budget_version_history"),
    path("configuration/", budget_views.configuration, name="configuration"),
    path("produits-budgetaires/", budget_views.budget_products, name="budget_products"),
    path("gestion-budgets/", budget_views.versions, name="budget_versions"),
    path("gestion-budgets/<int:pk>/", budget_views.version_detail, name="budget_version"),
    path("gestion-budgets/<int:pk>/import-excel/", budget_views.allocation_import, name="allocation_import"),
    path("gestion-budgets/<int:pk>/supprimer/", budget_views.version_delete, name="budget_version_delete"),
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
