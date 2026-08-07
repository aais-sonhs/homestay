from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import (
    Branch,
    BranchMembership,
    HousekeepingActivityLog,
    HousekeepingTask,
    IssueTicket,
    QCTask,
    Room,
    Shift,
    SupplyRequest,
    TaskChecklistItem,
    TaskPause,
    TaskPhoto,
)
from .services import (
    HousekeepingError,
    accept_task,
    complete_task,
    create_supply_request,
    pause_task,
    report_issue,
    resume_task,
    review_qc,
    scoped_tasks,
    start_task,
    update_checklist_item,
)


CONTEXT = {"ip": "127.0.0.1", "device_id": "test-device"}


class HousekeepingWorkflowTests(TestCase):
    def setUp(self):
        self.hk1 = User.objects.create_user(username="hk1", password="Test@2026", role=User.Role.HOUSEKEEPING)
        self.hk2 = User.objects.create_user(username="hk2", password="Test@2026", role=User.Role.HOUSEKEEPING)
        self.qc = User.objects.create_user(username="qc-test", password="Test@2026", role=User.Role.QC)
        self.manager = User.objects.create_user(username="manager-test", password="Test@2026", role=User.Role.MANAGER)
        self.branch_a = Branch.objects.create(
            code="A", name="Chi nhánh A", owner=self.manager
        )
        self.branch_b = Branch.objects.create(
            code="B", name="Chi nhánh B", owner=self.manager
        )
        for user in (self.hk1, self.hk2):
            BranchMembership.objects.create(user=user, branch=self.branch_a)
        BranchMembership.objects.create(
            user=self.qc,
            branch=self.branch_a,
            membership_role=BranchMembership.MembershipRole.QC,
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch_a,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch_b,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch_a,
            code="DAY",
            name="Ca ngày",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=8),
        )
        self.shift_b = Shift.objects.create(
            branch=self.branch_b,
            code="DAY",
            name="Ca ngày",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=8),
        )
        self.counter = 0

    def make_task(self, *, branch=None, status=HousekeepingTask.Status.UNASSIGNED, assignee=None, shift=True, requires_qc=True):
        self.counter += 1
        branch = branch or self.branch_a
        room = Room.objects.create(
            branch=branch,
            code=f"R{self.counter:03}",
            name=f"Phòng {self.counter}",
            status=Room.Status.WAITING_CLEANING,
        )
        selected_shift = (self.shift if branch == self.branch_a else self.shift_b) if shift else None
        return HousekeepingTask.objects.create(
            code=f"TASK-{self.counter:03}",
            branch=branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            priority=HousekeepingTask.Priority.HIGH,
            status=status,
            assignee=assignee,
            shift=selected_shift,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=1),
            requires_qc=requires_qc,
        )

    def add_item(self, task, *, key="required", requires_photo=False, status=TaskChecklistItem.Status.PENDING):
        return TaskChecklistItem.objects.create(
            task=task,
            definition_key=key,
            title=f"Checklist {key}",
            is_required=True,
            requires_photo=requires_photo,
            status=status,
        )

    def test_scope_only_returns_authorized_branch(self):
        allowed = self.make_task()
        hidden = self.make_task(branch=self.branch_b)
        ids = set(scoped_tasks(self.hk1).values_list("id", flat=True))
        self.assertIn(allowed.id, ids)
        self.assertNotIn(hidden.id, ids)

    def test_accept_records_assignee_timestamp_history_and_activity(self):
        task = self.make_task()
        result = accept_task(self.hk1, task.id, task.version, CONTEXT)
        self.assertEqual(result.status, HousekeepingTask.Status.ACCEPTED)
        self.assertEqual(result.assignee, self.hk1)
        self.assertIsNotNone(result.accepted_at)
        self.assertEqual(result.version, 2)
        self.assertTrue(result.status_history.filter(to_status=HousekeepingTask.Status.ACCEPTED).exists())
        self.assertTrue(result.activity_logs.filter(action="TASK_ACCEPTED", user=self.hk1).exists())

    def test_second_housekeeper_cannot_accept_taken_task(self):
        task = self.make_task()
        accept_task(self.hk1, task.id, task.version, CONTEXT)
        with self.assertRaises(HousekeepingError) as raised:
            accept_task(self.hk2, task.id, 1, CONTEXT)
        self.assertEqual(raised.exception.code, "TASK_ALREADY_ASSIGNED")
        task.refresh_from_db()
        self.assertEqual(task.assignee, self.hk1)

    def test_accept_outside_shift_is_rejected(self):
        task = self.make_task()
        self.shift.starts_at = timezone.now() - timedelta(hours=3)
        self.shift.ends_at = timezone.now() - timedelta(hours=2)
        self.shift.save()
        with self.assertRaises(HousekeepingError) as raised:
            accept_task(self.hk1, task.id, task.version, CONTEXT)
        self.assertEqual(raised.exception.code, "USER_NOT_ON_SHIFT")

    def test_start_and_checklist_update_task_and_room(self):
        task = self.make_task(status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk1)
        item_one = self.add_item(task, key="one")
        self.add_item(task, key="two")
        task = start_task(self.hk1, task.id, task.version, CONTEXT)
        task.room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingTask.Status.IN_PROGRESS)
        self.assertEqual(task.room.status, Room.Status.CLEANING)
        self.assertIsNotNone(task.started_at)
        item_one, task = update_checklist_item(
            self.hk1,
            task.id,
            item_one.id,
            {"version": task.version, "status": "COMPLETED", "value": True},
            CONTEXT,
        )
        self.assertEqual(task.progress_percent, 50)
        self.assertEqual(item_one.completed_by, self.hk1)
        self.assertIsNotNone(item_one.completed_at)

    def test_pause_and_resume_preserve_pause_period(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        task = pause_task(self.hk1, task.id, task.version, "GUEST_IN_ROOM", "Khách chưa ra ngoài", CONTEXT)
        self.assertEqual(task.status, HousekeepingTask.Status.PAUSED)
        task = resume_task(self.hk1, task.id, task.version, CONTEXT)
        pause = TaskPause.objects.get(task=task)
        self.assertEqual(task.status, HousekeepingTask.Status.IN_PROGRESS)
        self.assertIsNotNone(pause.resumed_at)
        self.assertEqual(pause.resumed_by, self.hk1)

    def test_supply_request_is_idempotent_and_linked_to_branch(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        payload = {
            "items": [{"inventoryItemId": "TOWEL", "quantity": 2, "unit": "Cái"}],
            "priority": "HIGH",
            "clientRequestId": "offline-001",
        }
        first, created = create_supply_request(self.hk1, task.id, payload, CONTEXT)
        second, created_again = create_supply_request(self.hk1, task.id, payload, CONTEXT)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.branch, self.branch_a)
        self.assertEqual(SupplyRequest.objects.count(), 1)

    def test_blocking_issue_links_task_and_room_and_blocks_resume(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        issue, created = report_issue(
            self.hk1,
            task.id,
            {"issueType": "DEVICE_NOT_WORKING", "severity": "HIGH", "description": "Điều hòa hỏng", "blocksRoomReady": True},
            CONTEXT,
        )
        task.refresh_from_db()
        task.room.refresh_from_db()
        self.assertTrue(created)
        self.assertEqual(issue.task, task)
        self.assertEqual(issue.room, task.room)
        self.assertEqual(task.status, HousekeepingTask.Status.WAITING_SUPPORT)
        self.assertEqual(task.room.status, Room.Status.CLEANING_BLOCKED)
        with self.assertRaises(HousekeepingError) as raised:
            resume_task(self.hk1, task.id, task.version, CONTEXT)
        self.assertEqual(raised.exception.code, "BLOCKING_ISSUE_EXISTS")

    def test_completion_requires_checklist_and_required_photo(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        item = self.add_item(task, requires_photo=True)
        with self.assertRaises(HousekeepingError) as raised:
            complete_task(self.hk1, task.id, task.version, True, "", CONTEXT)
        self.assertEqual(raised.exception.code, "CHECKLIST_REQUIRED_INCOMPLETE")
        item.status = TaskChecklistItem.Status.COMPLETED
        item.completed_by = self.hk1
        item.completed_at = timezone.now()
        item.save()
        with self.assertRaises(HousekeepingError) as raised:
            complete_task(self.hk1, task.id, task.version, True, "", CONTEXT)
        self.assertEqual(raised.exception.code, "REQUIRED_PHOTO_MISSING")

    def test_completion_qc_reject_rework_and_second_qc_round(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        item = self.add_item(task, requires_photo=True, status=TaskChecklistItem.Status.COMPLETED)
        TaskPhoto.objects.create(
            task=task,
            checklist_item=item,
            uploaded_by=self.hk1,
            category=TaskPhoto.Category.AFTER,
            image="housekeeping/test-after.jpg",
        )
        task = complete_task(self.hk1, task.id, task.version, True, "Đã xong", CONTEXT)
        task.room.refresh_from_db()
        self.assertEqual(task.status, HousekeepingTask.Status.WAITING_QC)
        self.assertEqual(task.room.status, Room.Status.WAITING_QC)
        self.assertEqual(task.qc_rounds.count(), 1)
        task, first_qc = review_qc(self.qc, task.id, task.version, False, "Gương còn bẩn", "Lau lại", CONTEXT)
        self.assertEqual(task.status, HousekeepingTask.Status.QC_REJECTED)
        self.assertEqual(first_qc.status, QCTask.Status.REJECTED)
        task = start_task(self.hk1, task.id, task.version, CONTEXT)
        self.assertEqual(task.rework_count, 1)
        task = complete_task(self.hk1, task.id, task.version, True, "Đã lau lại", CONTEXT)
        self.assertEqual(task.status, HousekeepingTask.Status.WAITING_QC)
        self.assertEqual(task.qc_rounds.count(), 2)
        first_qc.refresh_from_db()
        self.assertEqual(first_qc.reason, "Gương còn bẩn")

    def test_api_list_filters_branch_code_and_default_shift(self):
        visible = self.make_task()
        self.make_task(branch=self.branch_b)
        client = Client()
        client.force_login(self.hk1)
        response = client.get(reverse("housekeeping:api-task-list"), {"branchId": "A"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["data"][0]["id"], str(visible.id))
        web = client.get(reverse("housekeeping:task-list"), {"branchId": "A"})
        self.assertEqual(web.status_code, 200)
        self.assertContains(web, visible.code)
        self.assertContains(web, "Chưa có")

    def test_api_detects_stale_version_and_web_page_renders(self):
        task = self.make_task(status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk1)
        client = Client()
        client.force_login(self.hk1)
        response = client.post(
            reverse("housekeeping:api-start", kwargs={"task_id": task.id}),
            data='{"version": 99}',
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="legacy-stale-version-test",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "TASK_VERSION_CONFLICT")
        page = client.get(reverse("housekeeping:task-detail", kwargs={"task_id": task.id}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, task.code)

    def test_activity_log_contains_device_and_ip(self):
        task = self.make_task()
        accept_task(self.hk1, task.id, task.version, CONTEXT)
        log = HousekeepingActivityLog.objects.get(task=task, action="TASK_ACCEPTED")
        self.assertEqual(log.ip_address, "127.0.0.1")
        self.assertEqual(log.device_id, "test-device")

    def test_issue_client_id_does_not_create_duplicates(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk1)
        payload = {
            "issueType": "OTHER",
            "severity": "NORMAL",
            "description": "Vết nứt nhỏ",
            "blocksRoomReady": False,
            "clientRequestId": "offline-issue-1",
        }
        first, _ = report_issue(self.hk1, task.id, payload, CONTEXT)
        second, created = report_issue(self.hk1, task.id, payload, CONTEXT)
        self.assertFalse(created)
        self.assertEqual(first.id, second.id)
        self.assertEqual(IssueTicket.objects.count(), 1)
