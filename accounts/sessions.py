from uuid import uuid4

from .models import ActiveLogin


ACTIVE_LOGIN_TOKEN = "active_login_token"


def register_active_login(sender, request, user, **kwargs):
    token = uuid4().hex
    ActiveLogin.objects.update_or_create(user=user, defaults={"token": token})
    request.session[ACTIVE_LOGIN_TOKEN] = token
