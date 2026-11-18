from django.urls import path

from . import views

app_name = "hr"
urlpatterns = [
    path("", views.employees, name="employees"),
    path("nouveau/", views.employee_edit, name="employee_new"),
    path("<int:pk>/", views.employee_detail, name="employee_detail"),
    path("<int:pk>/modifier/", views.employee_edit, name="employee_edit"),
    path("<int:pk>/paie/", views.payroll, name="payroll"),
]
