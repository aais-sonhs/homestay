from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import (
    Branch,
    BranchMembership,
    HousekeepingActivityLog,
    HousekeepingTask,
    IssueTicket,
    Notification,
    NotificationRecipient,
    QCTask,
    Room,
    Shift,
    SupplyRequest,
    SupplyRequestItem,
    TaskChecklistItem,
)


class Phase8FieldAppSourceContractTests(SimpleTestCase):
    """Phase 8 field UI keeps account, tabs, typed input and conflicts explicit."""

    def test_field_app_covers_tabs_typed_checklist_and_three_way_conflict_ui(self):
        root = Path(settings.BASE_DIR) / "housekeeping_app/lib/src"
        presentation = (root / "presentation/task_presentation.dart").read_text()
        checklist = (root / "widgets/checklist_editor.dart").read_text()
        conflict = (root / "widgets/conflict_resolution_sheet.dart").read_text()
        for tab in ("mine", "available", "inProgress", "support", "waitingQc", "rework", "done"):
            self.assertIn(tab, presentation)
        for item_type in (
            "CHECKBOX",
            "YES_NO",
            "NUMBER",
            "TEXT",
            "PHOTO",
            "SINGLE_SELECT",
            "MULTI_SELECT",
            "DEVICE_CHECK",
            "QR_SCAN",
        ):
            self.assertIn(item_type, checklist)
        for snapshot in ("baseSnapshot", "localOperation", "serverSnapshot"):
            self.assertIn(snapshot, conflict)

    def test_encrypted_cache_is_bound_to_user_and_logout_blocks_pending_work(self):
        root = Path(settings.BASE_DIR) / "housekeeping_app/lib/src"
        repository = (root / "offline/offline_repository.dart").read_text()
        home = (root / "screens/offline_home_screen.dart").read_text()
        self.assertIn("bindUser", repository)
        self.assertIn("owner_user_id", repository)
        self.assertIn("clearUserData", repository)
        self.assertIn("_pending > 0", home)


class Phase8BackofficeUITests(TestCase):
    """Phase 8: scoped operational UI for dispatch, QC, support and audit."""

    def setUp(self):
        self.manager = User.objects.create_user(
            username="phase8-manager",
            role=User.Role.MANAGER,
        )
        self.housekeeper = User.objects.create_user(
            username="phase8-housekeeper",
            first_name="Hương",
            role=User.Role.HOUSEKEEPING,
        )
        self.warehouse = User.objects.create_user(
            username="phase8-warehouse",
            role=User.Role.WAREHOUSE,
        )
        self.technician = User.objects.create_user(
            username="phase8-technician",
            role=User.Role.TECHNICIAN,
        )
        self.outsider = User.objects.create_user(
            username="phase8-outsider",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(code="P8-A", name="Phase 8 Đà Lạt")
        self.other_branch = Branch.objects.create(code="P8-B", name="Phase 8 Hà Nội")
        for user, role in (
            (self.manager, BranchMembership.MembershipRole.MANAGER),
            (self.housekeeper, BranchMembership.MembershipRole.HOUSEKEEPER),
            (self.warehouse, BranchMembership.MembershipRole.WAREHOUSE),
            (self.technician, BranchMembership.MembershipRole.TECHNICIAN),
        ):
            BranchMembership.objects.create(
                user=user,
                branch=self.branch,
                membership_role=role,
            )
        BranchMembership.objects.create(
            user=self.outsider,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="P8-SHIFT",
            name="Ca sáng Phase 8",
            starts_at=now - timedelta(hours=2),
            ends_at=now + timedelta(hours=6),
        )
        self.room = Room.objects.create(
            branch=self.branch,
            code="P8-101",
            name="Phòng P8-101",
            floor="Tầng 1",
            area="Khu A",
            status=Room.Status.CLEANING,
        )
        self.task = HousekeepingTask.objects.create(
            code="P8-TASK-A",
            branch=self.branch,
            room=self.room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            priority=HousekeepingTask.Priority.URGENT,
            assignee=self.housekeeper,
            shift=self.shift,
            scheduled_start_at=now - timedelta(hours=1),
            due_at=now - timedelta(minutes=20),
            next_checkin_at=now + timedelta(minutes=25),
            started_at=now - timedelta(minutes=40),
            progress_percent=50,
            special_request="Không dùng nước hoa phòng",
        )
        self.item = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="p8-minibar-temperature",
            group_name="Minibar",
            title="Kiểm tra nhiệt độ minibar",
            item_type=TaskChecklistItem.ItemType.NUMBER,
            validation_snapshot={"min": 2, "max": 8},
        )
        qc_room = Room.objects.create(
            branch=self.branch,
            code="P8-102",
            name="Phòng P8-102",
            status=Room.Status.WAITING_QC,
        )
        self.qc_task = HousekeepingTask.objects.create(
            code="P8-TASK-QC",
            branch=self.branch,
            room=qc_room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.WAITING_QC,
            assignee=self.housekeeper,
            shift=self.shift,
            scheduled_start_at=now - timedelta(hours=2),
            due_at=now + timedelta(minutes=20),
            completed_at=now - timedelta(minutes=5),
        )
        TaskChecklistItem.objects.create(
            task=self.qc_task,
            definition_key="p8-qc-item",
            group_name="Phòng ngủ",
            title="Kiểm tra ga giường",
            status=TaskChecklistItem.Status.COMPLETED,
        )
        QCTask.objects.create(task=self.qc_task, round_number=1)
        self.supply = SupplyRequest.objects.create(
            task=self.task,
            branch=self.branch,
            requested_by=self.housekeeper,
            priority=HousekeepingTask.Priority.HIGH,
            note="Cần gấp trước check-in",
        )
        SupplyRequestItem.objects.create(
            request=self.supply,
            inventory_item_id="TOWEL",
            item_name="Khăn tắm",
            quantity=2,
            unit="Cái",
        )
        self.issue = IssueTicket.objects.create(
            task=self.task,
            room=self.room,
            reported_by=self.housekeeper,
            issue_type="LOCK_BROKEN",
            severity=HousekeepingTask.Priority.URGENT,
            description="Khóa cửa không hoạt động",
            blocks_room_ready=True,
        )
        HousekeepingActivityLog.objects.create(
            task=self.task,
            branch=self.branch,
            user=self.housekeeper,
            action="CHECKLIST_ITEM_UPDATED",
            correlation_id="phase8-visible-correlation",
            changes={"itemId": str(self.item.id)},
        )
        other_room = Room.objects.create(
            branch=self.other_branch,
            code="P8-SECRET",
            name="Phòng ngoài scope",
        )
        other_task = HousekeepingTask.objects.create(
            code="P8-SECRET-TASK",
            branch=self.other_branch,
            room=other_room,
            scheduled_start_at=now,
            due_at=now + timedelta(hours=1),
        )
        HousekeepingActivityLog.objects.create(
            task=other_task,
            branch=self.other_branch,
            user=self.outsider,
            action="TASK_VIEWED",
            correlation_id="phase8-secret-correlation",
        )
        notification = Notification.objects.create(
            branch=self.branch,
            task=self.task,
            notification_type="TASK_ASSIGNED",
            title="Task cần xử lý",
            body="Phòng P8-101 sắp check-in",
        )
        self.recipient = NotificationRecipient.objects.create(
            notification=notification,
            user=self.housekeeper,
        )

    def authenticated(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_operations_dashboard_renders_sla_team_progress_and_qc_queue(self):
        response = self.authenticated(self.manager).get(
            reverse("housekeeping:operations-dashboard"),
            {"date": timezone.localdate().isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Điều phối và thời hạn xử lý")
        self.assertContains(response, "P8-TASK-A")
        self.assertContains(response, "Nguy cơ trễ giờ nhận phòng")
        self.assertContains(response, "P8-TASK-QC")
        self.assertContains(response, "Hiệu suất theo nhân viên")

    def test_task_list_and_detail_expose_full_filters_typed_checklist_and_qc_form(self):
        list_response = self.authenticated(self.housekeeper).get(
            reverse("housekeeping:task-list"),
            {"area": "Khu A", "floor": "Tầng 1", "checkinRisk": "true"},
        )
        detail_response = self.authenticated(self.manager).get(
            reverse("housekeeping:task-detail", kwargs={"task_id": self.qc_task.id})
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Nguy cơ trễ giờ nhận phòng")
        self.assertContains(list_response, "Loại phòng")
        self.assertContains(list_response, "Ca làm việc")
        self.assertContains(list_response, self.shift.name)
        for tab_label in (
            "Việc của tôi",
            "Chờ nhận",
            "Đang thực hiện",
            "Chờ hỗ trợ",
            "Chờ kiểm tra chất lượng",
            "Cần làm lại",
            "Đã hoàn thành",
        ):
            self.assertContains(list_response, tab_label)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Điều phối công việc")
        self.assertContains(detail_response, "Hạng mục không đạt")
        self.assertContains(detail_response, "Kiểm tra ga giường")

    def test_backoffice_support_waiting_qc_and_done_tabs_match_field_app(self):
        now = timezone.now()
        support_room = Room.objects.create(
            branch=self.branch,
            code="P8-103",
            name="Phòng P8-103",
            status=Room.Status.CLEANING_BLOCKED,
        )
        support_task = HousekeepingTask.objects.create(
            code="P8-TASK-SUPPORT",
            branch=self.branch,
            room=support_room,
            status=HousekeepingTask.Status.WAITING_SUPPORT,
            assignee=self.housekeeper,
            shift=self.shift,
            scheduled_start_at=now,
            due_at=now + timedelta(hours=1),
        )
        done_room = Room.objects.create(
            branch=self.branch,
            code="P8-104",
            name="Phòng P8-104",
            status=Room.Status.READY,
        )
        done_task = HousekeepingTask.objects.create(
            code="P8-TASK-DONE",
            branch=self.branch,
            room=done_room,
            status=HousekeepingTask.Status.QC_APPROVED,
            assignee=self.housekeeper,
            shift=self.shift,
            scheduled_start_at=now,
            due_at=now + timedelta(hours=1),
            completed_at=now,
        )
        client = self.authenticated(self.housekeeper)

        support = client.get(reverse("housekeeping:task-list"), {"tab": "support"})
        waiting_qc = client.get(
            reverse("housekeeping:task-list"), {"tab": "waiting-qc"}
        )
        done = client.get(reverse("housekeeping:task-list"), {"tab": "done"})

        self.assertContains(support, support_task.code)
        self.assertNotContains(support, self.task.code)
        self.assertContains(waiting_qc, self.qc_task.code)
        self.assertContains(done, done_task.code)
        self.assertNotContains(done, support_task.code)

    def test_dashboard_uses_localized_status_due_time_and_duration_units(self):
        response = self.authenticated(self.manager).get(
            reverse("housekeeping:operations-dashboard"),
            {"date": timezone.localdate().isoformat()},
        )

        local_due = timezone.localtime(self.task.due_at).strftime("%H:%M %d/%m/%Y")
        self.assertContains(response, self.task.get_status_display())
        self.assertContains(response, local_due)
        self.assertNotContains(response, self.task.due_at.isoformat())
        self.assertContains(response, "phút")

    def test_navigation_keeps_current_section_and_manages_mobile_menu_focus(self):
        client = self.authenticated(self.manager)
        tasks = client.get(reverse("housekeeping:task-list"))
        operations = client.get(reverse("housekeeping:operations-dashboard"))
        base_source = (
            Path(settings.BASE_DIR) / "static/js/housekeeping.js"
        ).read_text()

        self.assertContains(
            tasks,
            'href="/housekeeping/tasks/" aria-current="page"',
            html=False,
        )
        self.assertContains(
            operations,
            'href="/housekeeping/operations/" aria-current="page"',
            html=False,
        )
        self.assertIn('navPanel?.querySelector(\'[aria-current="page"]\')', base_source)
        self.assertIn('event.key !== "Escape"', base_source)
        self.assertIn('navPanel.classList.contains("is-open")', base_source)

    def test_warehouse_and_technician_can_operate_their_scoped_queues(self):
        warehouse = self.authenticated(self.warehouse)
        supply_page = warehouse.get(reverse("housekeeping:support-queue"))
        supply_update = warehouse.post(
            reverse(
                "housekeeping:support-web-action",
                kwargs={"entity_type": "supply", "entity_id": self.supply.id},
            ),
            {"version": self.supply.version, "status": "ACKNOWLEDGED", "note": "Đang soạn kho"},
        )
        technician = self.authenticated(self.technician)
        issue_page = technician.get(reverse("housekeeping:support-queue"))
        issue_update = technician.post(
            reverse(
                "housekeeping:support-web-action",
                kwargs={"entity_type": "issue", "entity_id": self.issue.id},
            ),
            {"version": self.issue.version, "status": "IN_PROGRESS", "note": "Đang kiểm tra"},
        )

        self.assertContains(supply_page, "Khăn tắm")
        self.assertEqual(supply_update.status_code, 302)
        self.assertContains(issue_page, "Khóa cửa không hoạt động")
        self.assertEqual(issue_update.status_code, 302)
        self.supply.refresh_from_db()
        self.issue.refresh_from_db()
        self.assertEqual(self.supply.status, SupplyRequest.Status.ACKNOWLEDGED)
        self.assertEqual(self.issue.status, IssueTicket.Status.IN_PROGRESS)

    def test_activity_and_notification_centers_enforce_user_scope(self):
        client = self.authenticated(self.housekeeper)
        activity = client.get(reverse("housekeeping:activity-log"))
        notification = client.get(reverse("housekeeping:notification-center"))
        read = client.post(
            reverse(
                "housekeeping:notification-web-read",
                kwargs={"recipient_id": self.recipient.id},
            )
        )

        self.assertContains(activity, "phase8-visible-correlation")
        self.assertNotContains(activity, "phase8-secret-correlation")
        self.assertContains(notification, "công việc cần xử lý")
        self.assertContains(notification, "1 thông báo chưa đọc")
        self.assertEqual(read.status_code, 302)
        self.recipient.refresh_from_db()
        self.assertIsNotNone(self.recipient.read_at)

    def test_field_user_cannot_open_support_backoffice(self):
        response = self.authenticated(self.housekeeper).get(
            reverse("housekeeping:support-queue")
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("housekeeping:task-list"))
