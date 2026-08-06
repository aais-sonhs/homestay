"""PostgreSQL-only test settings for row-lock/concurrency verification.

Run only through Django's test command. Django creates and destroys `test_homestay`;
the `homestay` development database is never used as the test database.
"""

import os

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "homestay",
        "USER": "postgres",
        "PASSWORD": os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", "")),
        "HOST": os.environ.get("PGHOST", "localhost"),
        "PORT": os.environ.get("PGPORT", "5432"),
        "TEST": {"NAME": "test_homestay"},
    }
}
