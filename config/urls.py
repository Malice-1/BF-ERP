"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from accounts import views as account_views
from budgeting import views as budget_views

urlpatterns = [
    path('', RedirectView.as_view(pattern_name='purchasing:list', permanent=False)),
    path('connexion/', auth_views.LoginView.as_view(template_name='purchasing/login.html'), name='login'),
    path('deconnexion/', auth_views.LogoutView.as_view(), name='logout'),
    path('achats/', include('purchasing.urls')),
    path('habilitations/', account_views.authorization_list, name='authorizations'),
    path('habilitations/nouvelle/', account_views.authorization_edit, name='authorization_create'),
    path('habilitations/<int:pk>/version/', account_views.authorization_edit, name='authorization_edit'),
    path('responsables-cdf/', budget_views.manager_list, name='managers'),
    path('responsables-cdf/nouveau/', budget_views.manager_edit, name='manager_create'),
    path('responsables-cdf/<int:pk>/cloturer/', budget_views.manager_edit, name='manager_end'),
    path('admin/', admin.site.urls),
]
