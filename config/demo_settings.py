"""Local persistent demo, without PostgreSQL concurrency guarantees."""
from .settings import *  # noqa: F403

DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.demo.sqlite3"}}
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
