from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import User


DEMO_PASSWORD = "Demo@2026Safe"
DEMO_USERS = (
    ("admin", "admin@blisshome.test", "0901000002", User.Role.FOUNDER, True),
    ("manager", "manager@blisshome.test", "0901000003", User.Role.MANAGER, False),
    ("housekeeping", "housekeeping@blisshome.test", "0901000004", User.Role.HOUSEKEEPING, False),
    ("qc", "qc@blisshome.test", "0901000005", User.Role.QC, False),
    ("technician", "technician@blisshome.test", "0901000006", User.Role.TECHNICIAN, False),
    ("warehouse", "warehouse@blisshome.test", "0901000007", User.Role.WAREHOUSE, False),
    ("customer_service", "cskh@blisshome.test", "0901000008", User.Role.CUSTOMER_SERVICE, False),
    (
        "housekeeping_lead",
        "housekeeping_lead@blisshome.test",
        "0901000009",
        User.Role.HOUSEKEEPING,
        False,
    ),
    ("viewer", "viewer@blisshome.test", "0901000010", User.Role.CUSTOMER_SERVICE, False),
)

RETIRED_DEMO_USERS = (("founder", "founder@blisshome.test"),)


class Command(BaseCommand):
    help = "Tạo tài khoản demo cho toàn bộ vai trò Bliss Home."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Đặt lại mật khẩu của cả tài khoản demo đã tồn tại.",
        )

    def handle(self, *args, **options):
        for username, email in RETIRED_DEMO_USERS:
            retired_user = User.objects.filter(username=username, email=email).first()
            if retired_user is None:
                continue
            retired_user.role = User.Role.FOUNDER
            retired_user.is_active = False
            retired_user.is_staff = False
            retired_user.is_superuser = False
            retired_user.set_unusable_password()
            retired_user.save()
            revoked_at = timezone.now()
            retired_user.access_tokens.filter(revoked_at__isnull=True).update(
                revoked_at=revoked_at
            )
            retired_user.refresh_tokens.filter(revoked_at__isnull=True).update(
                revoked_at=revoked_at
            )
            self.stdout.write(f"- {username:<18} đã vô hiệu hóa; dùng tài khoản admin")

        created_count = 0
        for username, email, phone, role, is_admin in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "phone_number": phone,
                    "role": role,
                    "is_active": True,
                    "is_staff": is_admin,
                    "is_superuser": username == "admin",
                },
            )
            if created or options["reset_passwords"]:
                user.email = email
                user.phone_number = phone
                user.role = role
                user.is_active = True
                user.is_staff = is_admin
                user.is_superuser = username == "admin"
                user.is_deleted = False
                user.is_permanently_disabled = False
                user.disabled_by_admin = False
                user.locked_due_to_failed_logins = False
                user.set_password(DEMO_PASSWORD)
                user.save()
            created_count += int(created)
            state = "đã tạo" if created else "đã có"
            self.stdout.write(f"- {username:<18} {email:<30} {state}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Hoàn tất: tạo mới {created_count}/{len(DEMO_USERS)} tài khoản. "
                f"Mật khẩu mặc định: {DEMO_PASSWORD}"
            )
        )
