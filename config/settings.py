import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_APP_DIR = LOG_DIR / "app"
LOG_SERVER_DIR = LOG_DIR / "server"

SECRET_KEY = "4zC8pN7vQ2xK9mT5rW1sH6fD3jL0bY8uA4eG7cR2nM9qP5kX1tV6wS3hF0dJ8zB"
DEBUG = False
ALLOWED_HOSTS = [
    "homestay.aaistech.com",
    "113.160.218.241",
    "127.0.0.1",
    "localhost",
]
CSRF_TRUSTED_ORIGINS = [
    "http://homestay.aaistech.com",
    "https://homestay.aaistech.com",
    "http://113.160.218.241:8020",
    "https://113.160.218.241:8020",
    "http://127.0.0.1:8020",
    "https://127.0.0.1:8020",
]
# Giống Fasthub: lớp proxy bên ngoài xử lý TLS, Uvicorn vẫn nhận HTTP ở 8020.
# Không ép scheme để cả HTTP trực tiếp và HTTPS qua proxy đều hoạt động.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "housekeeping",
    "organizations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "common.api_auth.BearerAuthenticationMiddleware",
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
        'PASSWORD': 'TuanHai2508',
        'HOST': '14.224.220.54',
        'PORT': '5432',
    }
}

# Test suite luôn dùng SQLite in-memory và không ghi vào PostgreSQL local.
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
    ALLOWED_HOSTS.append("testserver")
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

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

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
MEDIA_URL = "/media/"
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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "suppress_not_found": {"()": "common.logging_filters.SuppressNotFoundFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(name)s %(funcName)s:%(lineno)d %(levelname)s %(message)s",
            "datefmt": "%d/%m/%Y %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["suppress_not_found"],
        },
        "app_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_APP_DIR / "app.log"),
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf8",
            "delay": True,
            "formatter": "verbose",
        },
        "server_file": {
            "class": "logging.handlers.TimedRotatingFileHandler",
            "filename": str(LOG_SERVER_DIR / "server.log"),
            "when": "midnight",
            "backupCount": 30,
            "encoding": "utf8",
            "delay": True,
            "formatter": "verbose",
            "filters": ["suppress_not_found"],
        },
    },
    "loggers": {
        "django.server": {
            "handlers": ["console", "server_file"],
            "level": "INFO",
            "propagate": False,
        },
        "housekeeping": {
            "handlers": ["console", "app_file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
