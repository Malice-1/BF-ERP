from django.apps import apps


APP_LABELS = {
    "accounts": "Comptes et accès", "budgeting": "Budgets", "purchasing": "Achats",
    "suppliers": "Fournisseurs", "workflow": "Historique et suivi",
    "auth": "Authentification", "admin": "Administration", "sessions": "Sessions",
    "receiving": "Réceptions", "accounting": "Comptabilité", "documents": "Documents",
    "contenttypes": "Types de données",
}
MODEL_LABELS = {
    "user": "utilisateur", "role": "rôle ERP", "validationfunction": "fonction de validation",
    "authorization": "habilitation", "authorizationversion": "version d’habilitation",
    "sessionpolicy": "politique de déconnexion", "costcenter": "CDF",
    "funding": "financement", "budgetproduct": "produit budgétaire (BI)",
    "detailedproduct": "produit détaillé", "budget": "budget historique",
    "budgetline": "ligne de budget historique", "costcentermanagerassignment": "affectation de responsable CDF",
    "annualenvelope": "enveloppe budgétaire annuelle", "envelopeversion": "version budgétaire",
    "allocation": "allocation budgétaire TVAC", "budgetentry": "écriture budgétaire",
    "purchaserequest": "demande d’achat", "purchaserequestline": "ligne de demande d’achat",
    "workflowversion": "configuration des validations", "approvalrule": "règle de validation",
    "submission": "cycle de soumission", "linesnapshot": "instantané de ligne",
    "approvalstep": "étape de validation", "purchaseorder": "bon de commande",
    "delegation": "délégation", "purchasenotice": "notification d’achat",
    "supplier": "fournisseur", "suppliercontact": "contact fournisseur", "supplieraddress": "adresse fournisseur",
    "auditevent": "événement d’achat", "configurationauditevent": "événement de configuration",
    "activitylog": "journal des actions", "group": "groupe", "permission": "permission",
    "logentry": "entrée du journal d’administration", "session": "session", "contenttype": "type de données",
}
ACTIONS = {"add": "Ajouter", "change": "Modifier", "delete": "Supprimer", "view": "Consulter"}


def permission_label(permission):
    ct = permission.content_type
    app = APP_LABELS.get(ct.app_label, ct.app_label)
    model = MODEL_LABELS.get(ct.model, ct.model)
    return f"{app} | {model} | {permission.name}"


def localize_permissions(sender=None, using="default", **kwargs):
    Permission = apps.get_model("auth", "Permission")
    for permission in Permission.objects.using(using).select_related("content_type"):
        model = permission.content_type.model
        for action, verb in ACTIONS.items():
            if permission.codename == f"{action}_{model}" and model in MODEL_LABELS:
                name = f"{verb} : {MODEL_LABELS[model]}"
                if permission.name != name:
                    Permission.objects.using(using).filter(pk=permission.pk).update(name=name)
                break
