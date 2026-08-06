import json

from django.contrib.auth import authenticate
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from accounts.management.commands.seed_demo_data import (
    DEMO_PASSWORD,
    DEMO_USERS,
    RETIRED_DEMO_USERS,
)
from accounts.models import AccessToken, RefreshToken, User
from organizations.models import BranchMembership


MEMBERSHIP_LABELS = {
    "housekeeping_lead": BranchMembership.MembershipRole.HOUSEKEEPING_LEAD.label,
    "viewer": BranchMembership.MembershipRole.VIEWER.label,
}

COMMON_WEB_ROUTES = (
    "housekeeping:task-list",
    "housekeeping:operations-dashboard",
    "housekeeping:activity-log",
    "housekeeping:notification-center",
    "password-change",
    "avatar-update",
)
CREATE_TASK_USERS = {"admin", "manager"}
SUPPORT_QUEUE_USERS = {"admin", "manager", "warehouse", "technician"}
TASK_READER_USERS = {
    "admin",
    "manager",
    "housekeeping",
    "housekeeping_lead",
    "qc",
    "customer_service",
    "viewer",
}


class Command(BaseCommand):
    help = "Kiểm tra đăng nhập web, API và phạm vi quyền của toàn bộ tài khoản demo."

    def handle(self, *args, **options):
        failures = []
        verified = []

        for username, email in RETIRED_DEMO_USERS:
            retired_user = User.objects.filter(username=username, email=email).first()
            if retired_user is None:
                continue
            if retired_user.is_active or retired_user.is_staff or retired_user.is_superuser:
                failures.append(f"{username}: tài khoản quản trị cũ chưa được vô hiệu hóa")
            if authenticate(username=username, password=DEMO_PASSWORD) is not None:
                failures.append(f"{username}: tài khoản quản trị cũ vẫn đăng nhập được")
            retired_api_response = Client().post(
                reverse("api-token-login"),
                data=json.dumps(
                    {"identifier": username, "password": DEMO_PASSWORD}
                ),
                content_type="application/json",
            )
            if retired_api_response.status_code != 401:
                failures.append(
                    f"{username}: API của tài khoản cũ trả về "
                    f"{retired_api_response.status_code}, cần 401"
                )

        for username, _email, _phone, _role, is_admin in DEMO_USERS:
            user = User.objects.filter(username=username).first()
            if user is None:
                failures.append(f"{username}: chưa có tài khoản")
                continue

            role_label = MEMBERSHIP_LABELS.get(username, user.get_role_display())
            if authenticate(username=username, password=DEMO_PASSWORD) is None:
                failures.append(f"{username}: xác thực mật khẩu thất bại")
                continue

            session_client = Client()
            login_response = session_client.post(
                reverse("public-login"),
                {"username": username, "password": DEMO_PASSWORD},
            )
            if login_response.status_code != 302 or login_response.url != reverse(
                "housekeeping:task-list"
            ):
                failures.append(
                    f"{username}: đăng nhập web trả về {login_response.status_code}"
                )
                continue

            task_response = session_client.get(reverse("housekeeping:task-list"))
            visible_text = task_response.content.decode("utf-8", errors="ignore")
            if task_response.status_code != 200:
                failures.append(
                    f"{username}: danh sách công việc trả về {task_response.status_code}"
                )
                continue
            for expected_text in (username, "Đổi mật khẩu", "Đăng xuất"):
                if expected_text not in visible_text:
                    failures.append(
                        f"{username}: menu tài khoản thiếu nội dung {expected_text!r}"
                    )

            for route_name in COMMON_WEB_ROUTES:
                route_response = session_client.get(reverse(route_name))
                if route_response.status_code != 200:
                    failures.append(
                        f"{username}: {route_name} trả về {route_response.status_code}, cần 200"
                    )

            create_response = session_client.get(reverse("housekeeping:task-create"))
            expected_create_status = 200 if username in CREATE_TASK_USERS else 302
            if create_response.status_code != expected_create_status:
                failures.append(
                    f"{username}: tạo công việc trả về {create_response.status_code}, "
                    f"cần {expected_create_status}"
                )
            create_link = f'href="{reverse("housekeeping:task-create")}"'
            if (create_link in visible_text) != (username in CREATE_TASK_USERS):
                failures.append(f"{username}: hiển thị sai menu tạo công việc")

            support_response = session_client.get(reverse("housekeeping:support-queue"))
            expected_support_status = 200 if username in SUPPORT_QUEUE_USERS else 302
            if support_response.status_code != expected_support_status:
                failures.append(
                    f"{username}: hàng đợi hỗ trợ trả về {support_response.status_code}, "
                    f"cần {expected_support_status}"
                )

            admin_response = session_client.get(reverse("admin:index"))
            expected_admin_status = 200 if is_admin else 302
            if admin_response.status_code != expected_admin_status:
                failures.append(
                    f"{username}: trang quản trị trả về {admin_response.status_code}, "
                    f"cần {expected_admin_status}"
                )
            has_admin_menu = "Quản trị hệ thống" in visible_text
            if has_admin_menu != is_admin:
                failures.append(f"{username}: hiển thị sai menu quản trị hệ thống")

            logout_response = session_client.post(reverse("logout"))
            protected_after_logout = session_client.get(reverse("housekeeping:task-list"))
            if logout_response.status_code != 302 or protected_after_logout.status_code != 302:
                failures.append(f"{username}: đăng xuất web hoặc khóa phiên thất bại")

            api_response = Client().post(
                reverse("api-token-login"),
                data=json.dumps(
                    {
                        "identifier": username,
                        "password": DEMO_PASSWORD,
                        "deviceName": "Kiểm tra tài khoản theo vai trò",
                    }
                ),
                content_type="application/json",
            )
            if api_response.status_code != 201:
                failures.append(
                    f"{username}: đăng nhập API trả về {api_response.status_code}"
                )
                continue

            token_data = api_response.json()["data"]
            access_key = token_data["accessToken"]
            refresh_key = token_data["refreshToken"]
            api_client = Client(HTTP_AUTHORIZATION=f"Bearer {access_key}")
            api_tasks = api_client.get(reverse("housekeeping:api-task-list"))
            visible_task_count = 0
            if api_tasks.status_code != 200:
                failures.append(
                    f"{username}: API danh sách công việc trả về {api_tasks.status_code}"
                )
            else:
                visible_task_count = api_tasks.json()["pagination"]["total"]
                if username in TASK_READER_USERS and visible_task_count == 0:
                    failures.append(
                        f"{username}: được cấp quyền xem nhưng không thấy công việc nào"
                    )
            api_logout = api_client.post(
                reverse("api-token-logout"),
                data=json.dumps({"refreshToken": refresh_key}),
                content_type="application/json",
            )
            if api_logout.status_code != 200:
                failures.append(
                    f"{username}: đăng xuất API trả về {api_logout.status_code}"
                )

            AccessToken.objects.filter(key=access_key).delete()
            RefreshToken.objects.filter(key=refresh_key).delete()
            verified.append((username, role_label, visible_task_count))

        if failures:
            raise CommandError("Kiểm tra thất bại:\n- " + "\n- ".join(failures))

        for username, role_label, visible_task_count in verified:
            self.stdout.write(
                f"- {username:<18} {role_label:<32} "
                f"web/menu/phạm vi/API/đăng xuất đạt; thấy {visible_task_count} công việc"
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Đã kiểm tra thành công {len(verified)}/{len(DEMO_USERS)} tài khoản: "
                "đăng nhập web, menu tài khoản, phân quyền quản trị, API và đăng xuất; "
                "tài khoản founder cũ đã bị khóa."
            )
        )
