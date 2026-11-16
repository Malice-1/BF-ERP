"""Isolated PostgreSQL acceptance settings; override TEST_PG_* as needed."""
import os
from .test_settings import *  # noqa: F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": os.getenv("TEST_PG_DATABASE", "bf_erp_validation"),
    "USER": os.getenv("TEST_PG_USER", "erp_test"),
    "PASSWORD": os.getenv("TEST_PG_PASSWORD", ""),
    "HOST": os.getenv("TEST_PG_HOST", "127.0.0.1"),
    "PORT": os.getenv("TEST_PG_PORT", "55432"),
    "OPTIONS": {"connect_timeout": 5},
}}
