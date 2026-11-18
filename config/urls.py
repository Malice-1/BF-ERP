"""Application routes and compatibility redirects for retired screens."""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from accounts import views as account_views
from accounts.auth_views import ERPLoginView
from budgeting import views as budget_views
from purchasing import flow_views
from budgeting import transfer_views
from receiving.views import stock, stock_movements, stock_balances, warehouses, purchase_receipts, purchase_receive

urlpatterns = [
    path("comptabilite/", include("accounting.urls")),
    path("rh/", include("hr.urls")),
    path("ventes/", include("sales.urls")),
    path("stocks/", stock, name="stock"),
    path("stocks/mouvements/", stock_movements, name="stock_movements"),
    path("stocks/receptions/", purchase_receipts, name="purchase_receipts"),
    path("stocks/receptions/<int:pk>/", purchase_receive, name="purchase_receive"),
    path("stocks/quantites/", stock_balances, name="stock_balances"),
    path("stocks/depots/", warehouses, name="warehouses"),
    path("stocks/depots/<int:pk>/", warehouses, name="warehouse_edit"),
    path("budget/transferts/", transfer_views.transfer_list, name="transfer_list"),
    path("budget/transferts/suivi/", transfer_views.transfer_monitor, name="transfer_monitor"),
    path("budget/transferts/groupes/<int:pk>/valider/", transfer_views.transfer_batch_approve, name="transfer_batch_approve"),
    path("budget/transferts/groupes/<int:pk>/cloturer/", transfer_views.transfer_batch_close, name="transfer_batch_close"),
    path("budget/transferts/<int:pk>/corriger/", transfer_views.transfer_correct, name="transfer_correct"),
    path("budget/versions/<int:version_id>/transferts/", transfer_views.version_transfers, name="version_transfers"),
    path("budget/transferts/<int:pk>/parcours/", transfer_views.transfer_timeline, name="transfer_timeline"),
    path("budget/transferts/<int:pk>/", transfer_views.transfer_detail, name="transfer_detail"),
    path("mes-validations/", flow_views.inbox, name="my_validations"),
    path("mes-delegations/", flow_views.delegations, name="my_delegations"),
    path("configuration/responsables/", budget_views.entity_managers, name="entity_managers"),
    path('configuration/session/', account_views.session_settings, name='session_settings'),
    path('session/statut/', account_views.session_status, name='session_status'),
    path('', RedirectView.as_view(pattern_name='purchasing:list', permanent=False)),
    path('connexion/', ERPLoginView.as_view(), name='login'),
    path('deconnexion/', auth_views.LogoutView.as_view(), name='logout'),
    path('achats/', include('purchasing.urls')),
    path('habilitations/', account_views.authorization_list, name='authorizations'),
    path('habilitations/nouvelle/', account_views.authorization_edit, name='authorization_create'),
    path('habilitations/<int:pk>/version/', account_views.authorization_edit, name='authorization_edit'),
    path('responsables-cdf/', budget_views.retired_manager_editor, name='managers'),
    path('responsables-cdf/nouveau/', budget_views.retired_manager_editor, name='manager_create'),
    path('responsables-cdf/<int:pk>/cloturer/', budget_views.retired_manager_editor, name='manager_end'),
    path('admin/', admin.site.urls),
]
