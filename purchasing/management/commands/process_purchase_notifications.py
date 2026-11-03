from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from purchasing.models import PurchaseNotice, Submission
from purchasing.flow import refresh_submission


class Command(BaseCommand):
    help = "Actualise les habilitations des workflows et traite la file durable de courriels. À planifier périodiquement."

    def add_arguments(self, parser):
        parser.add_argument("--recover", action="store_true", help="Réexaminer les échecs permanents après rétablissement du service.")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        for pk in Submission.objects.filter(active=True).values_list("pk", flat=True):
            refresh_submission(pk)
        states = ["pending", "failed"] + (["permanent"] if options["recover"] else [])
        ids = list(PurchaseNotice.objects.filter(email_state__in=states).filter(
            Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now())).order_by("pk").values_list("pk", flat=True)[:max(0, options["limit"])])
        sent = 0
        for pk in ids:
            with transaction.atomic():
                notice = PurchaseNotice.objects.select_for_update(of=("self",)).select_related("recipient", "step__snapshot__submission").get(pk=pk)
                if notice.email_state not in states:
                    continue
                # No current actionable business state => no resend.
                relevant = notice.active and notice.recipient is not None and notice.recipient.is_active and notice.step_id and notice.step.snapshot.submission.active
                if not relevant:
                    notice.email_state = "obsolete"
                    notice.save(update_fields=["email_state"])
                    continue
                notice.attempts += 1
                try:
                    if not notice.recipient.email:
                        raise ValueError("Adresse de courriel absente.")
                    send_mail("BF ERP · Validation d'achat", notice.message + "\n" + settings.ERP_BASE_URL.rstrip("/") + "/achats/validations/",
                        settings.DEFAULT_FROM_EMAIL, [notice.recipient.email], fail_silently=False)
                    notice.email_state, notice.retry_at = "sent", None
                    sent += 1
                except Exception:
                    # A delivery failure never rolls back the business decision.
                    notice.email_state = "permanent" if notice.attempts >= settings.PURCHASE_EMAIL_MAX_ATTEMPTS else "failed"
                    notice.retry_at = timezone.now() + timedelta(seconds=settings.PURCHASE_EMAIL_RETRY_SECONDS)
                    self.stderr.write(f"Échec courriel notification {notice.pk} ({notice.email_state}).")
                notice.save(update_fields=["attempts", "email_state", "retry_at"])
        self.stdout.write(f"{sent} courriel(s) envoyé(s).")
