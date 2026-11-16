from django import template
from django.urls import reverse

register = template.Library()

WORKFLOW_MODELS = (
    ("accounts", "Role"),
    ("budgeting", "CostCenter"),
    ("budgeting", "Support"),
)
WORKFLOW_LABELS = {
    ("accounts", "Role"): "Rôles et permissions",
    ("budgeting", "CostCenter"): "CDF",
    ("budgeting", "Support"): "Supports",
}


@register.simple_tag(takes_context=True)
def grouped_admin_apps(context, app_list):
    """Regroup authorized admin entries without changing model permissions."""
    remaining, workflow, historical = [], {}, []
    for app in app_list:
        models = []
        for model in app["models"]:
            key = (app["app_label"], model["object_name"])
            if key in {("accounts", "Authorization"), ("accounts", "AuthorizationVersion")}:
                historical.append({**model, "name": str(model["name"]) + " (historique)"})
            elif key in WORKFLOW_MODELS:
                workflow[key] = {**model, "name": WORKFLOW_LABELS[key]}
            else:
                models.append(model)
        if models:
            remaining.append({**app, "models": models})
    models = [workflow[key] for key in WORKFLOW_MODELS if key in workflow]
    user = context["request"].user
    if models:
        remaining.insert(0, {"app_label": "workflow-settings", "name": "Responsables et validations",
                             "app_url": reverse("purchasing:configuration") + "#workflow-settings",
                             "models": models})
    if user.has_perm("accounts.manage_authorizations"):
        historical.append({"name": "Gérer les habilitations historiques", "object_name": "ManageAuthorizations",
                           "admin_url": reverse("authorizations"), "view_only": False})
    if historical:
        remaining.append({"app_label": "legacy-settings", "name": "Compatibilité des anciens circuits",
                          "app_url": reverse("purchasing:configuration") + "#legacy-settings", "models": historical})
    return remaining
