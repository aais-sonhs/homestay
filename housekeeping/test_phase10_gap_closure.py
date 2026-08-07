import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .models import (
    Area,
    Branch,
    BranchMembership,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    HousekeepingActivityLog,
    HousekeepingTask,
    NotificationRecipient,
    OfflineMutationReceipt,
    Room,
    Shift,
    Skill,
    TaskAssignment,
)
from .services import HousekeepingError, accept_task, reassign_task, scoped_tasks


CONTEXT = {
    "ip": "127.0.0.1",
    "device_id": "phase10-test-device",
    "correlation_id": "phase10-test-request",
    "idempotency_key": "",
}


class Phase10GapClosureTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="phase10-manager",
            role=User.Role.MANAGER,
        )
        self.worker = User.objects.create_user(
            username="phase10-worker",
            first_name="Lan",
            role=User.Role.HOUSEKEEPING,
        )
        self.unskilled = User.objects.create_user(
            username="phase10-unskilled",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="P10", name="Phase 10", owner=self.manager
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        self.worker_membership = BranchMembership.objects.create(
            user=self.worker,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        BranchMembership.objects.create(
            user=self.unskilled,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        self.area = Area.objects.create(branch=self.branch, code="P10-A", name="Khu A")
        self.worker_membership.areas.add(self.area)
        self.skill = Skill.objects.create(
            branch=self.branch,
            code="DEEP-CLEAN",
            name="Deep clean",
        )
        self.worker_membership.skills.add(self.skill)
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="P10-DAY",
            name="Ca ngày",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=7),
        )
        self.room = Room.objects.create(
            branch=self.branch,
            area_ref=self.area,
            area=self.area.name,
            code="P10-101",
            name="Phòng 101",
            status=Room.Status.DIRTY,
        )
        template = ChecklistTemplate.objects.create(
            branch=self.branch,
            code="P10-CHECKOUT",
            name="Checklist checkout",
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
        )
        self.checklist_version = ChecklistVersion.objects.create(
            template=template,
            version_number=1,
            version_label="v1",
            status=ChecklistVersion.Status.PUBLISHED,
            published_at=now,
            created_by=self.manager,
        )
        ChecklistItemDefinition.objects.create(
            version=self.checklist_version,
            key="BED",
            group_name="Phòng ngủ",
            title="Kiểm tra giường",
            item_type="CHECKBOX",
            required_photo_count=1,
            validation_rules={"required": True},
        )
        self.manager_token = AccessToken.objects.create(user=self.manager, label="P10 manager")
        self.worker_token = AccessToken.objects.create(user=self.worker, label="P10 worker")

    def api_client(self, token):
        return Client(HTTP_AUTHORIZATION=f"Bearer {token.key}")

    def create_payload(self, **overrides):
        now = timezone.now()
        payload = {
            "code": "P10-TASK-001",
            "branchId": str(self.branch.id),
            "roomId": str(self.room.id),
            "taskType": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            "priority": HousekeepingTask.Priority.HIGH,
            "shiftId": str(self.shift.id),
            "areaId": str(self.area.id),
            "checklistVersionId": str(self.checklist_version.id),
            "requiredSkillIds": [str(self.skill.id)],
            "scheduledStartAt": now.isoformat(),
            "dueAt": (now + timedelta(minutes=45)).isoformat(),
            "requiresQc": True,
        }
        payload.update(overrides)
        return payload

    def post_json(self, client, url, payload, key, *, method="post"):
        return getattr(client, method)(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_manager_creates_task_with_snapshot_skill_sla_and_notification(self):
        payload = self.create_payload(assigneeId=str(self.worker.id))
        response = self.post_json(
            self.api_client(self.manager_token),
            reverse("housekeeping:api-task-list"),
            payload,
            "phase10-create",
        )

        self.assertEqual(response.status_code, 201, response.content)
        task = HousekeepingTask.objects.get(code="P10-TASK-001")
        self.assertEqual(task.status, HousekeepingTask.Status.PENDING_ACCEPTANCE)
        self.assertEqual(task.assignee, self.worker)
        self.assertEqual(list(task.required_skills.all()), [self.skill])
        self.assertEqual(task.checklist_items.count(), 1)
        self.assertEqual(task.checklist_items.get().validation_snapshot["requiredPhotoCount"], 1)
        self.assertTrue(hasattr(task, "sla_state"))
        self.assertTrue(TaskAssignment.objects.filter(task=task, assignee=self.worker).exists())
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.worker,
                notification__notification_type="TASK_ASSIGNED",
                notification__task=task,
            ).exists()
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, Room.Status.WAITING_CLEANING)

        replay = self.post_json(
            self.api_client(self.manager_token),
            reverse("housekeeping:api-task-list"),
            payload,
            "phase10-create",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(HousekeepingTask.objects.filter(code="P10-TASK-001").count(), 1)

    def test_task_view_and_manager_note_are_audited_and_notified(self):
        create_response = self.post_json(
            self.api_client(self.manager_token),
            reverse("housekeeping:api-task-list"),
            self.create_payload(assigneeId=str(self.worker.id)),
            "phase10-create-view-note",
        )
        task_id = create_response.json()["data"]["taskId"]
        detail = self.api_client(self.worker_token).get(
            reverse("housekeeping:api-task-detail", args=[task_id])
        )
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(
            HousekeepingActivityLog.objects.filter(
                task_id=task_id,
                user=self.worker,
                action="TASK_VIEWED",
            ).exists()
        )

        task = HousekeepingTask.objects.get(pk=task_id)
        note_response = self.post_json(
            self.api_client(self.manager_token),
            reverse("housekeeping:api-task-note", args=[task.id]),
            {"version": task.version, "note": "Ưu tiên làm trước 14:00"},
            "phase10-manager-note",
            method="patch",
        )
        self.assertEqual(note_response.status_code, 200, note_response.content)
        self.assertTrue(
            HousekeepingActivityLog.objects.filter(
                task=task,
                action="MANAGER_NOTE_ADDED",
            ).exists()
        )
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.worker,
                notification__notification_type="MANAGER_NOTE_ADDED",
                notification__task=task,
            ).exists()
        )

    def test_required_skill_controls_visibility_accept_and_reassign(self):
        task = HousekeepingTask.objects.create(
            code="P10-SKILL-TASK",
            branch=self.branch,
            room=self.room,
            area=self.area,
            task_type=HousekeepingTask.TaskType.DEEP_CLEANING,
            status=HousekeepingTask.Status.UNASSIGNED,
            shift=self.shift,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(minutes=45),
        )
        task.required_skills.add(self.skill)

        self.assertIn(task.id, set(scoped_tasks(self.worker).values_list("id", flat=True)))
        self.assertNotIn(task.id, set(scoped_tasks(self.unskilled).values_list("id", flat=True)))
        with self.assertRaises(HousekeepingError) as missing_skill:
            accept_task(self.unskilled, task.id, task.version, CONTEXT)
        self.assertEqual(missing_skill.exception.code, "TASK_SKILL_NOT_ALLOWED")
        with self.assertRaises(HousekeepingError) as invalid_reassign:
            reassign_task(
                self.manager,
                task.id,
                self.unskilled.id,
                task.version,
                CONTEXT,
            )
        self.assertEqual(invalid_reassign.exception.code, "TASK_SKILL_NOT_ALLOWED")

    def test_offline_media_receipt_can_satisfy_camera_start_dependency(self):
        task = HousekeepingTask.objects.create(
            code="P10-CAMERA-TASK",
            branch=self.branch,
            room=self.room,
            area=self.area,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.ACCEPTED,
            assignee=self.worker,
            shift=self.shift,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(minutes=45),
        )
        client_media_id = "47b27fd9-4f33-49f5-8317-000000000010"
        response = self.api_client(self.worker_token).post(
            reverse("housekeeping:api-media", args=[task.id]),
            data={
                "version": task.version,
                "clientId": client_media_id,
                "category": "BEFORE",
                "source": "OFFLINE_CAMERA",
                "capturedAt": timezone.now().isoformat(),
                "metadata": "{}",
                "image": SimpleUploadedFile(
                    "before.jpg",
                    b"phase-10-camera-evidence",
                    content_type="image/jpeg",
                ),
            },
            HTTP_IDEMPOTENCY_KEY=client_media_id,
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(
            OfflineMutationReceipt.objects.filter(
                user=self.worker,
                task=task,
                operation="UPLOAD_MEDIA",
                client_mutation_id=client_media_id,
                status=OfflineMutationReceipt.Status.SUCCEEDED,
            ).exists()
        )


class Phase10SourceContractTests(SimpleTestCase):
    def test_mobile_uses_device_evidence_complete_filters_notifications_and_qc_media(self):
        root = Path(settings.BASE_DIR) / "housekeeping_app/lib/src"
        evidence = (root / "device/device_evidence.dart").read_text()
        detail = (root / "screens/offline_task_detail_screen.dart").read_text()
        filters = (root / "presentation/task_presentation.dart").read_text()
        notifications = (root / "screens/notification_screen.dart").read_text()
        for symbol in ("MobileScanner", "Geolocator.getCurrentPosition", "getWifiBSSID"):
            self.assertIn(symbol, evidence)
        for query in ("areaId", "shiftId", "status", "assignee", "qcRework"):
            self.assertIn(query, filters)
        self.assertIn("cameraPhotoClientId", detail)
        self.assertIn("qcMode", detail)
        self.assertIn("markNotificationRead", notifications)

    def test_startup_runs_sla_evaluator_without_managing_external_port(self):
        startup = (Path(settings.BASE_DIR) / "startup.sh").read_text()
        self.assertIn("evaluate_housekeeping_sla", startup)
        self.assertIn("ENABLE_SLA_WORKER", startup)
        self.assertIn('wait "$SERVER_PID"', startup)
