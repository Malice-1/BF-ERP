from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.http import require_http_methods
from .forms import AuthorizationForm
from .models import Authorization
from .services import publish_authorization


@login_required
@permission_required("accounts.manage_authorizations", raise_exception=True)
@require_http_methods(["GET"])
def authorization_list(request):
    return render(request, "accounts/authorizations.html", {"authorizations": Authorization.objects.select_related("user", "function", "current_version")})


@login_required
@permission_required("accounts.manage_authorizations", raise_exception=True)
@require_http_methods(["GET", "POST"])
def authorization_edit(request, pk=None):
    grant = get_object_or_404(Authorization, pk=pk) if pk else None
    initial = {}
    if grant:
        version = grant.current_version
        initial = dict(user=grant.user_id, function=grant.function_id, valid_from=version.valid_from,
            valid_until=version.valid_until, enabled=version.enabled, expected_version=version.version,
            cost_centers=version.scope.get("cost_center", []), fundings=version.scope.get("funding", []),
            budget_products=version.scope.get("budget_product", []))
    form = AuthorizationForm(request.POST if request.method == "POST" else None, initial=initial)
    if grant:
        form.fields["user"].disabled = True
        form.fields["function"].disabled = True
    if request.method == "POST" and form.is_valid():
        try:
            publish_authorization(actor=request.user, authorization_id=pk, **form.command_data())
            return redirect("authorizations")
        except ValidationError as error:
            for message in error.messages:
                form.add_error(None, message)
    return render(request, "purchasing/form.html", {"title": "Nouvelle version d’habilitation" if grant else "Nouvelle habilitation", "form": form})
