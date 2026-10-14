from django.urls import path
from . import views

app_name = "purchasing"
urlpatterns = [
    path("", views.request_list, name="list"),
    path("nouvelle/", views.request_create, name="create"),
    path("<int:pk>/", views.request_detail, name="detail"),
    path("<int:pk>/modifier/", views.request_edit, name="edit"),
    path("<int:pk>/annuler/", views.request_cancel, name="cancel"),
    path("<int:pk>/lignes/ajouter/", views.line_edit, name="line_add"),
    path("<int:pk>/lignes/<int:line_id>/modifier/", views.line_edit, name="line_edit"),
    path("<int:pk>/lignes/<int:line_id>/supprimer/", views.line_delete, name="line_delete"),
]
