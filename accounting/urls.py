from django.urls import path
from . import views
from . import supplier_views

app_name = "accounting"
urlpatterns = [
    path("factures-fournisseurs/", supplier_views.invoice_list, name="supplier_invoices"),
    path("factures-fournisseurs/importer/", supplier_views.upload, name="supplier_invoice_upload"),
    path("factures-fournisseurs/<int:pk>/", supplier_views.detail, name="supplier_invoice_detail"),
    path("factures-fournisseurs/<int:pk>/original/", supplier_views.download, name="supplier_invoice_download"),
    path("factures-fournisseurs/<int:pk>/revalider/", supplier_views.revalidate, name="supplier_invoice_revalidate"),
    path("factures-fournisseurs/<int:pk>/revoir/", supplier_views.review, name="supplier_invoice_review"),
    path("", views.home, name="home"),
    path("cadre/", views.profile, name="profile"),
    path("cadre/approuver/", views.approve, name="approve"),
    path("comptes/", views.accounts, name="accounts"),
    path("comptes/importer/", views.chart_import, name="chart_import"),
    path("comptes/nouveau/", views.account_edit, name="account_new"),
    path("comptes/<int:pk>/", views.account_edit, name="account_edit"),
    path("journaux/", views.journals, name="journals"),
    path("journaux/nouveau/", views.journal_edit, name="journal_new"),
    path("journaux/<int:pk>/", views.journal_edit, name="journal_edit"),
    path("exercices/", views.years, name="years"),
    path("exercices/nouveau/", views.year_new, name="year_new"),
    path("periodes/nouvelle/", views.period_new, name="period_new"),
    path("periodes/<int:pk>/<str:action>/", views.period_state, name="period_state"),
    path("ecritures/", views.entries, name="entries"),
    path("ecritures/nouvelle/", views.entry_edit, name="entry_new"),
    path("ecritures/<int:pk>/", views.entry_detail, name="entry_detail"),
    path("ecritures/<int:pk>/modifier/", views.entry_edit, name="entry_edit"),
    path("ecritures/<int:pk>/valider/", views.post, name="post"),
    path("ecritures/<int:pk>/contrepasser/", views.reverse, name="reverse"),
]
