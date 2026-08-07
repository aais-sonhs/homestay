import json
import re
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.contrib.sessions.models import Session
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    AccessToken,
    ActivityLog,
    PasswordHistory,
    PasswordResetRequest,
    RefreshToken,
    User,
)


class ForgotPasswordApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="housekeeper01",
            email="member@example.com",
            phone_number="0901234567",
            password="Current@2026Pass",
        )

    def post_json(self, name, payload, **headers):
        return self.client.post(
            reverse(name),
            data=json.dumps(payload),
            content_type="application/json",
            **headers,
        )

    def request_otp(self, identifier="member@example.com", channel="email"):
        response = self.post_json(
            "api-forgot-password-request",
            {"identifier": identifier, "channel": channel},
            HTTP_X_DEVICE_ID="android-test",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["requestId"]

    def email_otp(self, index=-1):
        match = re.search(r"\b(\d{6})\b", mail.outbox[index].body)
        self.assertIsNotNone(match)
        return match.group(1)

    def verified_token(self):
        request_id = self.request_otp()
        response = self.post_json(
            "api-forgot-password-verify-otp",
            {"requestId": request_id, "otp": self.email_otp()},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["resetToken"]

    def test_request_normalizes_email_and_never_stores_plain_otp(self):
        request_id = self.request_otp("  MEMBER@EXAMPLE.COM  ")

        reset_request = PasswordResetRequest.objects.get()
        otp = self.email_otp()
        self.assertEqual(request_id, reset_request.public_id)
        self.assertNotEqual(reset_request.otp_hash, otp)
        self.assertNotIn(otp, reset_request.otp_hash)
        self.assertEqual(reset_request.destination, "me****@example.com")
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.PENDING)
        self.assertEqual(len(otp), 6)

    def test_existing_and_unknown_accounts_receive_same_public_response(self):
        existing = self.post_json(
            "api-forgot-password-request",
            {"identifier": "member@example.com", "channel": "email"},
        )
        unknown = self.post_json(
            "api-forgot-password-request",
            {"identifier": "unknown@example.com", "channel": "email"},
        )

        self.assertEqual(existing.status_code, unknown.status_code)
        self.assertEqual(existing.json()["success"], unknown.json()["success"])
        self.assertEqual(existing.json()["message"], unknown.json()["message"])
        self.assertIn("requestId", unknown.json())
        self.assertEqual(PasswordResetRequest.objects.count(), 1)

    @patch("accounts.services.send_otp", side_effect=RuntimeError("provider unavailable"))
    def test_delivery_failure_does_not_reveal_existing_account(self, mocked_send):
        response = self.post_json(
            "api-forgot-password-request",
            {"identifier": "member@example.com", "channel": "email"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(
            PasswordResetRequest.objects.get().status,
            PasswordResetRequest.Status.CANCELLED,
        )

    def test_invalid_identifier_is_rejected(self):
        response = self.post_json(
            "api-forgot-password-request",
            {"identifier": "not-an-email", "channel": "email"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "INVALID_IDENTIFIER")

    @patch("accounts.services.send_otp")
    def test_phone_is_normalized_to_vietnam_e164(self, mocked_send):
        request_id = self.request_otp("090 123-4567", "sms")

        mocked_send.assert_called_once()
        self.assertEqual(mocked_send.call_args.kwargs["destination"], "+84901234567")
        self.assertEqual(PasswordResetRequest.objects.get().public_id, request_id)

    def test_correct_otp_returns_ten_minute_one_purpose_token(self):
        token = self.verified_token()
        reset_request = PasswordResetRequest.objects.get()

        self.assertTrue(token.startswith(f"{reset_request.public_id}."))
        self.assertNotIn(token, reset_request.reset_token_hash)
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.VERIFIED)
        remaining = (reset_request.reset_token_expires_at - timezone.now()).total_seconds()
        self.assertGreater(remaining, 590)
        self.assertLessEqual(remaining, 600)

    def test_wrong_otp_is_locked_after_five_attempts(self):
        request_id = self.request_otp()
        actual = self.email_otp()
        wrong = "000000" if actual != "000000" else "111111"

        for attempt in range(1, 6):
            response = self.post_json(
                "api-forgot-password-verify-otp",
                {"requestId": request_id, "otp": wrong},
            )
            self.assertEqual(response.status_code, 423 if attempt == 5 else 400)

        reset_request = PasswordResetRequest.objects.get()
        self.assertEqual(reset_request.failed_attempt_count, 5)
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.LOCKED)
        response = self.post_json(
            "api-forgot-password-verify-otp",
            {"requestId": request_id, "otp": actual},
        )
        self.assertEqual(response.json()["code"], "OTP_ATTEMPTS_EXCEEDED")

    def test_expired_otp_is_rejected(self):
        request_id = self.request_otp()
        reset_request = PasswordResetRequest.objects.get()
        reset_request.expires_at = timezone.now() - timedelta(seconds=1)
        reset_request.save(update_fields=["expires_at"])

        response = self.post_json(
            "api-forgot-password-verify-otp",
            {"requestId": request_id, "otp": self.email_otp()},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "OTP_EXPIRED")
        reset_request.refresh_from_db()
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.EXPIRED)

    def test_resend_obeys_cooldown_and_invalidates_old_otp(self):
        request_id = self.request_otp()
        old_otp = self.email_otp()

        too_soon = self.post_json(
            "api-forgot-password-resend-otp",
            {"requestId": request_id},
        )
        self.assertEqual(too_soon.status_code, 429)
        self.assertEqual(too_soon.json()["code"], "OTP_RESEND_TOO_SOON")

        reset_request = PasswordResetRequest.objects.get()
        reset_request.last_sent_at = timezone.now() - timedelta(seconds=61)
        reset_request.save(update_fields=["last_sent_at"])
        resent = self.post_json(
            "api-forgot-password-resend-otp",
            {"requestId": request_id},
        )
        self.assertEqual(resent.status_code, 200, resent.content)
        reset_request.refresh_from_db()
        self.assertEqual(reset_request.resend_count, 1)

        old_response = self.post_json(
            "api-forgot-password-verify-otp",
            {"requestId": request_id, "otp": old_otp},
        )
        self.assertEqual(old_response.json()["code"], "OTP_INVALID")

    def test_reset_updates_password_revokes_tokens_sessions_and_is_one_time(self):
        api_token = AccessToken.objects.create(user=self.user, label="old phone")
        refresh_token = RefreshToken.objects.create(
            user=self.user,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.force_login(self.user)
        session_key = self.client.session.session_key
        reset_token = self.verified_token()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.post_json(
                "api-forgot-password-reset",
                {
                    "resetToken": reset_token,
                    "newPassword": "BrandNew@2026Safe",
                    "confirmPassword": "BrandNew@2026Safe",
                },
            )

        self.assertEqual(response.status_code, 200, response.content)
        self.user.refresh_from_db()
        api_token.refresh_from_db()
        refresh_token.refresh_from_db()
        self.assertTrue(self.user.check_password("BrandNew@2026Safe"))
        self.assertIsNotNone(api_token.revoked_at)
        self.assertIsNotNone(refresh_token.revoked_at)
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        self.assertEqual(PasswordHistory.objects.filter(user=self.user).count(), 1)
        self.assertTrue(
            ActivityLog.objects.filter(
                user=self.user,
                event_type=ActivityLog.Event.COMPLETED,
                success=True,
            ).exists()
        )
        reused = self.post_json(
            "api-forgot-password-reset",
            {
                "resetToken": reset_token,
                "newPassword": "Another@2026Safe",
                "confirmPassword": "Another@2026Safe",
            },
        )
        self.assertEqual(reused.json()["code"], "RESET_TOKEN_INVALID")

    def test_password_confirmation_policy_and_reuse_are_enforced(self):
        token = self.verified_token()
        mismatch = self.post_json(
            "api-forgot-password-reset",
            {"resetToken": token, "newPassword": "Strong@2026Pass", "confirmPassword": "Other@2026Pass"},
        )
        self.assertEqual(mismatch.json()["code"], "PASSWORD_NOT_MATCH")

        weak = self.post_json(
            "api-forgot-password-reset",
            {"resetToken": token, "newPassword": "password", "confirmPassword": "password"},
        )
        self.assertEqual(weak.json()["code"], "PASSWORD_POLICY_FAILED")

        reused = self.post_json(
            "api-forgot-password-reset",
            {"resetToken": token, "newPassword": "Current@2026Pass", "confirmPassword": "Current@2026Pass"},
        )
        self.assertEqual(reused.json()["code"], "PASSWORD_REUSED")

    def test_expired_reset_token_is_rejected(self):
        token = self.verified_token()
        reset_request = PasswordResetRequest.objects.get()
        reset_request.reset_token_expires_at = timezone.now() - timedelta(seconds=1)
        reset_request.save(update_fields=["reset_token_expires_at"])

        response = self.post_json(
            "api-forgot-password-reset",
            {"resetToken": token, "newPassword": "NewSafe@2026Pass", "confirmPassword": "NewSafe@2026Pass"},
        )
        self.assertEqual(response.json()["code"], "RESET_TOKEN_EXPIRED")

    def test_account_and_ip_rate_limits(self):
        for _ in range(3):
            response = self.post_json(
                "api-forgot-password-request",
                {"identifier": "member@example.com", "channel": "email"},
                REMOTE_ADDR="10.1.1.1",
            )
            self.assertEqual(response.status_code, 200)
        limited = self.post_json(
            "api-forgot-password-request",
            {"identifier": "member@example.com", "channel": "email"},
            REMOTE_ADDR="10.1.1.1",
        )
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.json()["code"], "RATE_LIMIT_EXCEEDED")

        for _ in range(3):
            unknown = self.post_json(
                "api-forgot-password-request",
                {"identifier": "same-unknown@example.com", "channel": "email"},
                REMOTE_ADDR="10.3.3.3",
            )
            self.assertEqual(unknown.status_code, 200)
        unknown_limited = self.post_json(
            "api-forgot-password-request",
            {"identifier": "same-unknown@example.com", "channel": "email"},
            REMOTE_ADDR="10.3.3.3",
        )
        self.assertEqual(unknown_limited.status_code, 429)

        for index in range(10):
            response = self.post_json(
                "api-forgot-password-request",
                {"identifier": f"unknown{index}@example.com", "channel": "email"},
                REMOTE_ADDR="10.2.2.2",
            )
            self.assertEqual(response.status_code, 200)
        limited_ip = self.post_json(
            "api-forgot-password-request",
            {"identifier": "last@example.com", "channel": "email"},
            REMOTE_ADDR="10.2.2.2",
        )
        self.assertEqual(limited_ip.status_code, 429)

    def test_disabled_or_deleted_accounts_do_not_receive_otp(self):
        self.user.disabled_by_admin = True
        self.user.save(update_fields=["disabled_by_admin"])
        response = self.post_json(
            "api-forgot-password-request",
            {"identifier": self.user.email, "channel": "email"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(PasswordResetRequest.objects.exists())

    def test_activity_log_does_not_contain_otp_or_reset_token(self):
        token = self.verified_token()
        otp = self.email_otp()
        serialized = json.dumps(list(ActivityLog.objects.values()), default=str)
        self.assertNotIn(otp, serialized)
        self.assertNotIn(token, serialized)


class ForgotPasswordWebTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()

    def test_login_links_to_forgot_password_and_all_screens_render(self):
        login = self.client.get(reverse("login"))
        public_login = self.client.get("/login/")
        request_page = self.client.get(reverse("forgot-password"))
        done = self.client.get(reverse("forgot-password-done"))

        self.assertContains(login, reverse("forgot-password"))
        self.assertContains(login, "branding/bliss-homestay-logo.jpg?v=20260807-1")
        self.assertNotContains(login, "branding/bliss-home-mark.svg")
        self.assertEqual(public_login.status_code, 200)
        self.assertContains(request_page, "Gửi mã xác thực")
        self.assertContains(done, "Đăng nhập ngay")

    def test_dashboard_and_successful_login_redirect_to_housekeeping_tasks(self):
        user = User.objects.create_user(
            username="dashboard-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(response, reverse("housekeeping:task-list"))
        self.client.logout()
        login = self.client.post(
            reverse("login"),
            {"username": user.username, "password": "Current@2026Pass"},
        )
        self.assertRedirects(login, reverse("housekeeping:task-list"))

    def test_housekeeping_nav_account_menu_shows_profile_actions_but_hides_admin(self):
        user = User.objects.create_user(
            username="menu-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("housekeeping:task-list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="account-menu"')
        self.assertContains(response, "menu-user")
        self.assertContains(response, reverse("password-change"))
        self.assertContains(response, reverse("avatar-update"))
        self.assertContains(response, reverse("logout"))
        self.assertContains(response, reverse("documentation"))
        self.assertContains(response, "Tài liệu")
        self.assertNotContains(response, "Quản trị hệ thống")
        self.assertNotContains(response, ">Trang chủ</a>")

    def test_documentation_is_login_protected_and_renders_as_one_page(self):
        anonymous = self.client.get(reverse("documentation"))
        self.assertRedirects(
            anonymous,
            f'{reverse("login")}?next={reverse("documentation")}',
        )

        user = User.objects.create_user(
            username="documentation-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("documentation"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Tài liệu hệ thống Bliss Home")
        self.assertContains(response, "Một trang · Cuộn liên tục")
        self.assertContains(response, "https://homestay.aaistech.com")
        self.assertContains(response, 'id="mobile-api"')
        self.assertNotContains(response, 'class="pagination"')

    def test_superuser_keeps_system_admin_submenu_and_main_sidebar(self):
        user = User.objects.create_superuser(
            username="root-menu-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("housekeeping:task-list"))

        self.assertContains(response, "Quản trị hệ thống")
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, reverse("organizations:branch-list"))
        self.assertContains(response, reverse("organizations:branch-owner-list"))
        self.assertContains(response, "branding/bliss-homestay-logo.jpg?v=20260807-1")
        admin_page = self.client.get(reverse("admin:index"))
        self.assertContains(admin_page, "branding/bliss-homestay-logo.jpg?v=20260807-1")

    def test_avatar_update_uploads_and_removes_image(self):
        user = User.objects.create_user(
            username="avatar-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)
        avatar = SimpleUploadedFile(
            "avatar.gif",
            (
                b"GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!"
                b"\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
                b"\x00\x02\x02D\x01\x00;"
            ),
            content_type="image/gif",
        )

        response = self.client.post(reverse("avatar-update"), {"avatar": avatar}, follow=True)

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(user.avatar.name.startswith("avatars/"))
        self.assertContains(response, "Ảnh đại diện đã được cập nhật.")
        self.assertContains(response, f'src="{user.avatar.url}"')
        uploaded_name = user.avatar.name
        self.assertTrue(user.avatar.storage.exists(user.avatar.name))
        avatar_response = self.client.get(user.avatar.url)
        self.assertEqual(avatar_response.status_code, 200)
        self.assertEqual(avatar_response["Content-Type"], "image/gif")

        response = self.client.post(reverse("avatar-update"), {"remove_avatar": "on"}, follow=True)

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.avatar)
        self.assertFalse(user.avatar.storage.exists(uploaded_name))

    def test_avatar_update_rejects_non_image_file(self):
        user = User.objects.create_user(
            username="invalid-avatar-user",
            password="Current@2026Pass",
        )
        self.client.force_login(user)
        not_an_image = SimpleUploadedFile("avatar.txt", b"not an image", content_type="text/plain")

        response = self.client.post(reverse("avatar-update"), {"avatar": not_an_image})

        user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(user.avatar)
        self.assertIn("avatar", response.context["form"].errors)

    def test_authenticated_password_change_preserves_web_login_and_revokes_tokens(self):
        user = User.objects.create_user(
            username="password-menu-user",
            password="Current@2026Pass",
        )
        access = AccessToken.objects.create(user=user, label="old device")
        refresh = RefreshToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("password-change"),
            {
                "current_password": "Current@2026Pass",
                "new_password": "BrandNew@2027Safe",
                "confirm_password": "BrandNew@2027Safe",
            },
        )

        self.assertRedirects(response, reverse("housekeeping:task-list"))
        user.refresh_from_db()
        access.refresh_from_db()
        refresh.refresh_from_db()
        self.assertTrue(user.check_password("BrandNew@2027Safe"))
        self.assertIsNotNone(user.password_changed_at)
        self.assertIsNotNone(access.revoked_at)
        self.assertIsNotNone(refresh.revoked_at)
        self.assertEqual(PasswordHistory.objects.filter(user=user).count(), 1)
        self.assertEqual(str(self.client.session.get("_auth_user_id")), str(user.pk))

    def test_successful_web_reset_flushes_an_existing_login_session(self):
        user = User.objects.create_user(
            username="web-reset-user",
            email="web-reset@example.com",
            password="Current@2026Pass",
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("forgot-password"),
            {"identifier": user.email, "channel": "email"},
        )
        self.assertRedirects(response, reverse("forgot-password-otp"))
        otp = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        response = self.client.post(reverse("forgot-password-otp"), {"otp": otp})
        self.assertRedirects(response, reverse("forgot-password-reset"))
        response = self.client.post(
            reverse("forgot-password-reset"),
            {
                "new_password": "WebBrandNew@2026",
                "confirm_password": "WebBrandNew@2026",
            },
        )
        self.assertRedirects(response, reverse("forgot-password-done"))
        self.assertNotIn("_auth_user_id", self.client.session)
