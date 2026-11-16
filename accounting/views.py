from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import services
from .models import AccountingProfile, Account, FiscalYear, AccountingPeriod, Journal, JournalEntry
from .forms import (ProfileForm, AccountForm, ChartImportForm, JournalForm, YearForm, PeriodForm,
    EntryForm, EntryLineFormSet, RevisionForm, PeriodStateForm, ReversalForm)


def error_messages(error):
    return " ".join(error.messages)


@login_required
@require_GET
def home(request):
    if not any(p.startswith("accounting.") for p in request.user.get_all_permissions()):
        raise PermissionDenied
    return render(request, "accounting/home.html", {"profile": AccountingProfile.objects.filter(pk=1).first()})


@login_required
@permission_required("accounting.view_accountingprofile", raise_exception=True)
@require_http_methods(["GET", "POST"])
def profile(request):
    instance = AccountingProfile.objects.filter(pk=1).first() or AccountingProfile(pk=1)
    form = ProfileForm(request.POST or None, instance=instance)
    if request.method == "POST":
        services.require(request.user, "change_accountingprofile")
        if form.is_valid():
            try:
                services.configure_profile(actor=request.user, **form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error_messages(error))
            else:
                messages.success(request, "Cadre enregistré ; une approbation est nécessaire pour valider des écritures.")
                return redirect("accounting:profile")
    return render(request, "accounting/profile.html", {"form": form, "profile": instance,
        "approval_form": RevisionForm(initial={"revision": instance.revision})})


@login_required
@permission_required("accounting.approve_accountingprofile", raise_exception=True)
@require_POST
def approve(request):
    form = RevisionForm(request.POST)
    if form.is_valid():
        try:
            services.approve_profile(actor=request.user, **form.cleaned_data)
            messages.success(request, "Cadre et plan approuvés. Cette approbation interne doit s’appuyer sur une revue réglementaire réelle.")
        except ValidationError as error:
            messages.error(request, error_messages(error))
    else:
        messages.error(request, "Révision invalide.")
    return redirect("accounting:profile" if request.user.has_perm("accounting.view_accountingprofile") else "accounting:home")


@login_required
@permission_required("accounting.view_account", raise_exception=True)
@require_GET
def accounts(request):
    rows = Account.objects.all()
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(code__startswith=q) | Q(label__icontains=q))
    return render(request, "accounting/accounts.html", {"page": Paginator(rows, 100).get_page(request.GET.get("page")), "q": q})


@login_required
@permission_required("accounting.import_account", raise_exception=True)
@require_http_methods(["GET", "POST"])
def chart_import(request):
    form = ChartImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            uploaded = form.cleaned_data["file"]
            if uploaded.size > 2_000_000:
                raise ValidationError("Le fichier dépasse 2 Mo.")
            count = services.import_chart(actor=request.user, data=uploaded.read(), source_reference=form.cleaned_data["source_reference"])
        except ValidationError as error:
            form.add_error(None, error_messages(error))
        else:
            messages.success(request, f"Import terminé : {count} lignes. Un import identique n’est pas répété.")
            return redirect("accounting:accounts" if request.user.has_perm("accounting.view_account") else "accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Importer le plan applicable",
        "chart_template": True,
        "intro": "CSV UTF-8, séparateur point-virgule. En-têtes : code;label;postable;party_requirement. postable : 0 ou 1 ; party_requirement : NONE, CUSTOMER ou SUPPLIER. Aucun plan d’entreprise n’est imposé à l’organisme public."})


@login_required
@require_http_methods(["GET", "POST"])
def account_edit(request, pk=None):
    services.require(request.user, "change_account" if pk else "add_account")
    instance = get_object_or_404(Account, pk=pk) if pk else Account()
    form = AccountForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_account(actor=request.user, values=form.cleaned_data, pk=pk)
        except ValidationError as error:
            form.add_error(None, error_messages(error))
        else:
            messages.success(request, "Compte enregistré. Relisez et approuvez le plan avant de nouvelles validations.")
            return redirect("accounting:accounts" if request.user.has_perm("accounting.view_account") else "accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Compte général"})


@login_required
@permission_required("accounting.view_journal", raise_exception=True)
@require_GET
def journals(request):
    return render(request, "accounting/journals.html", {"rows": Journal.objects.all()})


@login_required
@require_http_methods(["GET", "POST"])
def journal_edit(request, pk=None):
    services.require(request.user, "change_journal" if pk else "add_journal")
    instance = get_object_or_404(Journal, pk=pk) if pk else Journal()
    form = JournalForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        try:
            services.save_journal(actor=request.user, values=form.cleaned_data, pk=pk)
        except ValidationError as error:
            form.add_error(None, error_messages(error))
        else:
            return redirect("accounting:journals" if request.user.has_perm("accounting.view_journal") else "accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Journal comptable"})


@login_required
@permission_required("accounting.view_fiscalyear", raise_exception=True)
@require_GET
def years(request):
    return render(request, "accounting/years.html", {"rows": FiscalYear.objects.prefetch_related("periods")})


@login_required
@permission_required("accounting.add_fiscalyear", raise_exception=True)
@require_http_methods(["GET", "POST"])
def year_new(request):
    form = YearForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.create_year(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error_messages(error))
        else:
            return redirect("accounting:years" if request.user.has_perm("accounting.view_fiscalyear") else "accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Nouvel exercice"})


@login_required
@permission_required("accounting.add_accountingperiod", raise_exception=True)
@require_http_methods(["GET", "POST"])
def period_new(request):
    form = PeriodForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.create_period(actor=request.user, **form.cleaned_data)
        except ValidationError as error:
            form.add_error(None, error_messages(error))
        else:
            return redirect("accounting:years" if request.user.has_perm("accounting.view_fiscalyear") else "accounting:home")
    return render(request, "accounting/form.html", {"form": form, "title": "Nouvelle période"})


@login_required
@require_POST
def period_state(request, pk, action):
    if action not in ("close", "reopen"):
        raise PermissionDenied
    services.require(request.user, "reopen_accountingperiod" if action == "reopen" else "lock_accountingperiod")
    get_object_or_404(AccountingPeriod, pk=pk)
    form = PeriodStateForm(request.POST)
    if form.is_valid():
        try:
            services.set_period_open(actor=request.user, pk=pk, is_open=action == "reopen", **form.cleaned_data)
            messages.success(request, "État de la période mis à jour. Cette opération ne constitue pas une clôture annuelle.")
        except ValidationError as error:
            messages.error(request, error_messages(error))
    else:
        messages.error(request, "Justification obligatoire.")
    return redirect("accounting:years" if request.user.has_perm("accounting.view_fiscalyear") else "accounting:home")


@login_required
@permission_required("accounting.view_journalentry", raise_exception=True)
@require_GET
def entries(request):
    rows = JournalEntry.objects.select_related("journal", "period__fiscal_year")
    q = request.GET.get("q", "").strip()
    if q:
        rows = rows.filter(Q(number__icontains=q) | Q(description__icontains=q) | Q(document_reference__icontains=q))
    if request.GET.get("status") in ("DRAFT", "POSTED"):
        rows = rows.filter(status=request.GET["status"])
    if request.GET.get("journal", "").isdigit():
        rows = rows.filter(journal_id=request.GET["journal"])
    for name, lookup in (("start", "gte"), ("end", "lte")):
        if request.GET.get(name):
            try:
                rows = rows.filter(**{f"accounting_date__{lookup}": date.fromisoformat(request.GET[name])})
            except ValueError:
                messages.error(request, "Date de filtre invalide.")
    return render(request, "accounting/entries.html", {"page": Paginator(rows, 50).get_page(request.GET.get("page")),
        "journals": Journal.objects.all()})


@login_required
@require_http_methods(["GET", "POST"])
def entry_edit(request, pk=None):
    services.require(request.user, "change_journalentry" if pk else "add_journalentry")
    instance = get_object_or_404(JournalEntry, pk=pk) if pk else JournalEntry()
    if instance.status != "DRAFT" or instance.reversal_of_id:
        raise PermissionDenied("Une écriture validée ne se modifie pas.")
    form = EntryForm(request.POST or None, instance=instance)
    lines = EntryLineFormSet(request.POST or None, instance=instance)
    if request.method == "POST":
        valid_form, valid_lines = form.is_valid(), lines.is_valid()
        if valid_form and valid_lines:
            try:
                result = services.save_draft(actor=request.user, pk=pk, revision=form.cleaned_data["revision"],
                    token=form.cleaned_data["token"], values={key: form.cleaned_data[key] for key in services.ENTRY_FIELDS},
                    lines=[{key: row.cleaned_data[key] for key in services.LINE_FIELDS}
                        for row in lines.forms if row.cleaned_data and not row.cleaned_data.get("DELETE")])
            except ValidationError as error:
                form.add_error(None, error_messages(error))
            else:
                messages.success(request, "Brouillon enregistré. La validation est une action distincte.")
                return redirect("accounting:entry_detail", pk=result.pk) if request.user.has_perm("accounting.view_journalentry") else redirect("accounting:home")
    return render(request, "accounting/entry_form.html", {"form": form, "lines": lines, "entry": instance})


@login_required
@permission_required("accounting.view_journalentry", raise_exception=True)
@require_GET
def entry_detail(request, pk):
    entry = get_object_or_404(JournalEntry.objects.select_related("period__fiscal_year", "journal", "reversal_of"), pk=pk)
    return render(request, "accounting/entry_detail.html", {"entry": entry,
        "rows": entry.lines.select_related("account", "customer", "supplier"),
        "post_form": RevisionForm(initial={"revision": entry.revision}), "reversal_form": ReversalForm()})


@login_required
@permission_required("accounting.post_journalentry", raise_exception=True)
@require_POST
def post(request, pk):
    get_object_or_404(JournalEntry, pk=pk)
    form = RevisionForm(request.POST)
    if form.is_valid():
        try:
            services.post_entry(actor=request.user, pk=pk, **form.cleaned_data)
            messages.success(request, "Écriture validée et numérotée.")
        except ValidationError as error:
            messages.error(request, error_messages(error))
    else:
        messages.error(request, "Révision invalide.")
    return redirect("accounting:entry_detail", pk=pk) if request.user.has_perm("accounting.view_journalentry") else redirect("accounting:home")


@login_required
@permission_required("accounting.reverse_journalentry", raise_exception=True)
@require_POST
def reverse(request, pk):
    get_object_or_404(JournalEntry, pk=pk)
    form = ReversalForm(request.POST)
    if form.is_valid():
        try:
            result = services.reverse_entry(actor=request.user, pk=pk, **form.cleaned_data)
            messages.success(request, "Contrepassation validée ; l’écriture d’origine est conservée.")
            return redirect("accounting:entry_detail", pk=result.pk) if request.user.has_perm("accounting.view_journalentry") else redirect("accounting:home")
        except ValidationError as error:
            messages.error(request, error_messages(error))
    else:
        messages.error(request, form.errors.as_text())
    return redirect("accounting:entry_detail", pk=pk) if request.user.has_perm("accounting.view_journalentry") else redirect("accounting:home")
