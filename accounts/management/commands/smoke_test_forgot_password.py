import re
from email import policy
from email.parser import BytesParser
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import ActivityLog, PasswordHistory, PasswordResetRequest, User


class Command(BaseCommand):
    help = "Chạy toàn bộ luồng quên mật khẩu trên cơ sở dữ liệu và dịch vụ thư cục bộ."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="housekeeping")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Smoke test chỉ được chạy khi DEBUG=1.")
        if not settings.EMAIL_BACKEND.endswith("filebased.EmailBackend"):
            raise CommandError("Kiểm thử nhanh cần dùng dịch vụ thư lưu tệp cục bộ.")

        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist:
            raise CommandError("Chưa có tài khoản demo. Hãy chạy seed_demo_data trước.") from None
        if not user.email:
            raise CommandError("Tài khoản kiểm thử nhanh phải có thư điện tử.")

        started_at = timezone.now()
        original_password = user.password
        original_changed_at = user.password_changed_at
        mailbox_path = Path(settings.EMAIL_FILE_PATH)
        mailbox_path.mkdir(parents=True, exist_ok=True)
        original_files = set(mailbox_path.iterdir())

        try:
            login_client = Client()
            login_response = login_client.post(
                reverse("login"),
                {"username": user.username, "password": "Demo@2026Safe"},
            )
            if login_response.status_code != 302:
                raise CommandError("Đăng nhập bằng tài khoản demo thất bại.")
            dashboard_response = login_client.get(reverse("dashboard"))
            if dashboard_response.status_code != 200:
                raise CommandError("Dashboard không truy cập được sau đăng nhập.")

            client = Client()
            request_response = client.post(
                reverse("forgot-password"),
                {"identifier": user.email, "channel": "email"},
            )
            if request_response.status_code != 302:
                raise CommandError("Bước gửi mã xác thực thất bại.")

            generated_files = set(mailbox_path.iterdir()) - original_files
            if not generated_files:
                raise CommandError("Thư chứa mã xác thực chưa được tạo trong hộp thư cục bộ.")
            otp_message_path = max(generated_files, key=lambda path: path.stat().st_mtime)
            with otp_message_path.open("rb") as message_file:
                email_message = BytesParser(policy=policy.default).parse(message_file)
            body_part = email_message.get_body(preferencelist=("plain",))
            body = body_part.get_content() if body_part else str(email_message.get_payload())
            match = re.search(r"\b\d{6}\b", body)
            if match is None:
                raise CommandError("Không tìm thấy mã xác thực 6 chữ số trong thư cục bộ.")

            verify_response = client.post(
                reverse("forgot-password-otp"),
                {"otp": match.group(0)},
            )
            if verify_response.status_code != 302:
                raise CommandError("Bước xác thực mã thất bại.")

            reset_response = client.post(
                reverse("forgot-password-reset"),
                {
                    "new_password": "SmokeTest@2026Safe",
                    "confirm_password": "SmokeTest@2026Safe",
                },
            )
            if reset_response.status_code != 302:
                raise CommandError("Bước đặt mật khẩu mới thất bại.")

            user.refresh_from_db()
            if not user.check_password("SmokeTest@2026Safe"):
                raise CommandError("Mật khẩu mới chưa được cập nhật.")
            reset_request = PasswordResetRequest.objects.filter(
                user=user,
                created_at__gte=started_at,
            ).latest("created_at")
            if reset_request.status != PasswordResetRequest.Status.COMPLETED:
                raise CommandError("Yêu cầu đặt lại mật khẩu chưa chuyển sang hoàn tất.")

            self.stdout.write(self.style.SUCCESS("PASS đăng nhập và dashboard"))
            self.stdout.write(self.style.SUCCESS("ĐẠT: gửi thư chứa mã xác thực cục bộ"))
            self.stdout.write(self.style.SUCCESS("ĐẠT: xác thực mã và mã đặt lại mật khẩu"))
            self.stdout.write(self.style.SUCCESS("ĐẠT: đổi mật khẩu và chuyển trạng thái hoàn tất"))
            self.stdout.write(self.style.SUCCESS("Luồng quên mật khẩu end-to-end hoạt động."))
        finally:
            User.objects.filter(pk=user.pk).update(
                password=original_password,
                password_changed_at=original_changed_at,
            )
            PasswordHistory.objects.filter(user=user, created_at__gte=started_at).delete()
            PasswordResetRequest.objects.filter(user=user, created_at__gte=started_at).delete()
            ActivityLog.objects.filter(user=user, created_at__gte=started_at).delete()
            for generated_path in set(mailbox_path.iterdir()) - original_files:
                if generated_path.is_file():
                    generated_path.unlink()
