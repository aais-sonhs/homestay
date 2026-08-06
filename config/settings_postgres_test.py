"""PostgreSQL-only test settings for row-lock/concurrency verification.

Run only through Django's test command. Django creates and destroys `test_homestay`;
the `homestay` development database is never used as the test database.
"""

from .settings import *  # noqa: F403


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "homestay",
        "USER": "postgres",
        "PASSWORD": "TuanHai2508",
        "HOST": "127.0.0.1",
        "PORT": "5432",
        "TEST": {"NAME": "test_homestay"},
    }
}
