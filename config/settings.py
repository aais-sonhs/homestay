import os
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "bliss-home-insecure-development-key",
)
DEBUG = True
ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "http://113.160.218.241:8020",
    "http://127.0.0.1:8020",
    "http://localhost:8020",
]
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "housekeeping",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "housekeeping.api.auth.BearerAuthenticationMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'homestay',                # tên DB trong DBeaver
        'USER': 'postgres',                 # user bạn dùng (thường là postgres)
        'PASSWORD': os.environ.get("DB_PASSWORD", os.environ.get("PGPASSWORD", "")),
        'HOST': os.environ.get("PGHOST", "localhost"),
        'PORT': os.environ.get("PGPORT", "5432"),
    }
}

# Test suite luôn dùng SQLite in-memory và không ghi vào PostgreSQL local.
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = []
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "housekeeping:task-list"
LOGOUT_REDIRECT_URL = "/accounts/login/"
CSRF_FAILURE_VIEW = "housekeeping.api.errors.csrf_failure"

# Số công việc tối đa một nhân viên Housekeeping được nhận đồng thời.
HOUSEKEEPING_CONCURRENT_TASK_LIMIT = 3
API_ACCESS_TOKEN_TTL_SECONDS = 3600
API_REFRESH_TOKEN_TTL_SECONDS = 2592000

# Cấu hình email local cố định; OTP không được in ra stdout/log.
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = BASE_DIR / ".local-emails"
if "test" in sys.argv:
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
DEFAULT_FROM_EMAIL = "Bliss Home <no-reply@blisshome.local>"
EMAIL_HOST = "localhost"
EMAIL_PORT = 587
EMAIL_HOST_USER = ""
EMAIL_HOST_PASSWORD = ""
EMAIL_USE_TLS = True
PASSWORD_RESET_SMS_BACKEND = "accounts.notifications.dummy_sms_backend"
PASSWORD_RESET_ALLOW_LOCAL_DELIVERY = True
PASSWORD_RESET_ENABLE_DEV_MAILBOX = True

PASSWORD_RESET_OTP_TTL_SECONDS = 300
PASSWORD_RESET_RESEND_AFTER_SECONDS = 60
PASSWORD_RESET_TOKEN_TTL_SECONDS = 600
PASSWORD_RESET_MAX_OTP_ATTEMPTS = 5
PASSWORD_RESET_ACCOUNT_LIMIT_15_MINUTES = 3
PASSWORD_RESET_ACCOUNT_LIMIT_24_HOURS = 5
PASSWORD_RESET_IP_LIMIT_24_HOURS = 10
