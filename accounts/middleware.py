from django.conf import settings
from django.contrib.auth import logout
from django.contrib.sessions.models import Session
from django.utils import timezone

from .models import ActiveLogin, SessionPolicy
from .sessions import ACTIVE_LOGIN_TOKEN


class IdleSessionMiddleware:
    """Enforce inactivity before any view, including admin and mutating requests."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            token = request.session.get(ACTIVE_LOGIN_TOKEN)
            if not token or not ActiveLogin.objects.filter(user=request.user, token=token).exists():
                logout(request)

        now = timezone.now().timestamp()
        timeout = SessionPolicy.timeout_seconds() if request.user.is_authenticated else None
        # Status polling must never extend a session.
        polling = request.path_info == "/session/statut/"
        if timeout is not None:
            last = request.session.get("last_activity_at")
            if last is None:
                # Existing sessions predate this middleware. Their original expiry
                # provides a conservative baseline instead of granting another 2h.
                expiry = Session.objects.filter(session_key=request.session.session_key).values_list("expire_date", flat=True).first()
                last = expiry.timestamp() - settings.SESSION_COOKIE_AGE if expiry else now
            if now - last > timeout:
                logout(request)
            elif not polling:
                request.session["last_activity_at"] = now
        response = self.get_response(request)
        # Login authenticates inside the view, after the check above.
        if request.user.is_authenticated and not polling:
            request.session["last_activity_at"] = now
        return response
