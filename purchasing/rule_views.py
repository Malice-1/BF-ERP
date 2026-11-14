"""Compatibility URLs for the retired configurable validation editor."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods


@login_required
@require_http_methods(["GET", "POST"])
def retired_editor(request, **kwargs):
    if request.method == "POST":
        return HttpResponse("Les circuits configurables ont été supprimés. Les validations suivent un parcours fixe.", status=410)
    return redirect("purchasing:configuration")


rule_sets = rule_set = rule_edit = rule_delete = simulate = retired_editor
