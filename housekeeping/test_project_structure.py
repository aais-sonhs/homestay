from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.template.loader import get_template

from housekeeping.models import Branch as HousekeepingBranch
from housekeeping.models import Room as HousekeepingRoom
from organizations.models import Branch, Room


class ProjectStructureTests(SimpleTestCase):
    def test_organization_facade_preserves_existing_model_identity(self):
        self.assertIs(Branch, HousekeepingBranch)
        self.assertIs(Room, HousekeepingRoom)

    def test_source_static_files_are_discoverable(self):
        self.assertEqual(settings.STATIC_URL, "/static/")
        self.assertIn(settings.BASE_DIR / "static", settings.STATICFILES_DIRS)
        self.assertIsNotNone(finders.find("css/housekeeping.css"))
        self.assertIsNotNone(finders.find("js/housekeeping.js"))
        self.assertIsNotNone(finders.find("branding/bliss-home-mark.svg"))

    def test_shared_templates_are_available(self):
        self.assertIsNotNone(get_template("base.html"))
        self.assertIsNotNone(get_template("shared/account_menu.html"))
        self.assertIsNotNone(get_template("shared/pagination.html"))

    def test_common_auth_middleware_is_configured(self):
        self.assertIn("common.api_auth.BearerAuthenticationMiddleware", settings.MIDDLEWARE)
        self.assertNotIn("housekeeping.api.auth.BearerAuthenticationMiddleware", settings.MIDDLEWARE)

    def test_http_and_proxy_https_are_both_allowed_on_port_8020(self):
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))
        self.assertIn("http://127.0.0.1:8020", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn("https://127.0.0.1:8020", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn("http://113.160.218.241:8020", settings.CSRF_TRUSTED_ORIGINS)
        self.assertIn("https://113.160.218.241:8020", settings.CSRF_TRUSTED_ORIGINS)
