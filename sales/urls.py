from django.urls import path
from . import views

app_name = "sales"
urlpatterns = [
    path("", views.home, name="home"),
    path("clients/", views.customers, name="customers"),
    path("clients/nouveau/", views.customer_edit, name="customer_new"),
    path("clients/<int:pk>/", views.customer_edit, name="customer_edit"),
    path("clients/<int:pk>/facturation/", views.customer_billing, name="customer_billing"),
    path("emetteur/", views.issuer, name="issuer"),
    path("formations/", views.trainings, name="trainings"),
    path("formations/nouvelle/", views.training_edit, name="training_new"),
    path("formations/<int:pk>/", views.training_edit, name="training_edit"),
    path("commandes/", views.orders, name="orders"),
    path("commandes/nouvelle/", views.order_edit, name="order_new"),
    path("commandes/<int:pk>/", views.order_detail, name="order_detail"),
    path("commandes/<int:pk>/modifier/", views.order_edit, name="order_edit"),
    path("commandes/<int:pk>/<str:action>/", views.order_action, name="order_action"),
    path("factures/", views.invoices, name="invoices"),
    path("factures/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("factures/<int:pk>/documents/<int:document_id>/", views.download, name="download"),
    path("factures/<int:pk>/documents/<int:document_id>/<str:action>/", views.document_action, name="document_action"),
    path("factures/<int:pk>/document/<str:action>/", views.document_action, name="regenerate"),
    path("factures/<int:pk>/paiements/", views.payment, name="payment"),
    path("factures/<int:pk>/paiements/<int:payment_id>/corriger/", views.payment_reverse, name="payment_reverse"),
    path("suivi/", views.report, name="report"),
]
