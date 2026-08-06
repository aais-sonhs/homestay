import json
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .models import (
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    HousekeepingTask,
    QCTask,
    ReworkRound,
    Room,
    Shift,
    TaskChecklistItem,
)
from .services import complete_task


CONTEXT = {
    "ip": "127.0.0.1",
    "device_id": "phase5-device",
    "correlation_id": "phase5-initial-complete",
    "idempotency_key": "",
}


class QCMultiRoundIntegrationTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.housekeeper = User.objects.create_user(
            username="phase5-housekeeper",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.qc_user = User.objects.create_user(
            username="phase5-qc",
            password="Test@2026",
            role=User.Role.QC,
        )
        branch = Branch.objects.create(code="PHASE5", name="Phase 5 Branch")
        BranchHousekeepingPolicy.objects.create(branch=branch, rework_failed_items_only=True)
        BranchMembership.objects.create(user=self.housekeeper, branch=branch)
        BranchMembership.objects.create(
            user=self.qc_user,
            branch=branch,
            membership_role=BranchMembership.MembershipRole.QC,
        )
        now = timezone.now()
        shift = Shift.objects.create(
            branch=branch,
            code="CURRENT",
            name="Ca hiện tại",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=5),
        )
        room = Room.objects.create(
            branch=branch,
            code="QC501",
            name="Phòng QC501",
            status=Room.Status.CLEANING,
        )
        self.task = HousekeepingTask.objects.create(
            code="PHASE5-TASK",
            branch=branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.housekeeper,
            shift=shift,
            scheduled_start_at=now - timedelta(minutes=30),
            due_at=now + timedelta(minutes=30),
            next_checkin_at=now + timedelta(hours=2),
        )
        self.failed_item = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="mirror",
            title="Lau gương",
            item_type=TaskChecklistItem.ItemType.CHECKBOX,
            status=TaskChecklistItem.Status.COMPLETED,
            value=True,
            completed_by=self.housekeeper,
            completed_at=now,
            sort_order=1,
        )
        self.good_item = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="bed",
            title="Kiểm tra giường",
            item_type=TaskChecklistItem.ItemType.CHECKBOX,
            status=TaskChecklistItem.Status.COMPLETED,
            value=True,
            completed_by=self.housekeeper,
            completed_at=now,
            sort_order=2,
        )
        self.task.progress_percent = 100
        self.task.save(update_fields=["progress_percent"])
        self.task = complete_task(
            self.housekeeper,
            self.task.id,
            self.task.version,
            True,
            "Dọn xong lần đầu",
            CONTEXT,
        )
        self.housekeeper_token = AccessToken.objects.create(user=self.housekeeper)
        self.qc_token = AccessToken.objects.create(user=self.qc_user)
        self.housekeeper_client = Client(
            HTTP_AUTHORIZATION=f"Bearer {self.housekeeper_token.key}"
        )
        self.qc_client = Client(HTTP_AUTHORIZATION=f"Bearer {self.qc_token.key}")

    def json_mutation(self, client, url, payload, key, *, method="post"):
        return getattr(client, method)(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key,
        )

    def test_qc_failed_items_media_deadline_and_second_round_are_immutable(self):
        first_qc = self.task.qc_rounds.get(round_number=1)
        original_checklist_snapshot = first_qc.checklist_snapshot
        qc_photo_response = self.qc_client.post(
            reverse("housekeeping:api-media", kwargs={"task_id": self.task.id}),
            {
                "version": self.task.version,
                "category": "QC",
                "source": "CAMERA",
                "qcRoundId": str(first_qc.id),
                "clientId": "qc-photo-round-1",
                "image": SimpleUploadedFile(
                    "qc-mirror.jpg",
                    b"qc-mirror-photo",
                    content_type="image/jpeg",
                ),
            },
            HTTP_IDEMPOTENCY_KEY="phase5-qc-photo",
        )
        self.assertEqual(qc_photo_response.status_code, 201)
        qc_photo_id = qc_photo_response.json()["data"]["photoId"]
        self.task.refresh_from_db()
        deadline = timezone.now() + timedelta(minutes=45)
        reject = self.json_mutation(
            self.qc_client,
            reverse(
                "housekeeping:api-qc-round-review",
                kwargs={"task_id": self.task.id, "round_number": 1},
            ),
            {
                "version": self.task.version,
                "approved": False,
                "reason": "Gương còn vệt nước",
                "note": "Lau và chụp lại ảnh",
                "deadlineAt": deadline.isoformat(),
                "mediaIds": [qc_photo_id],
                "failedItems": [
                    {
                        "checklistItemId": str(self.failed_item.id),
                        "reasonCode": "DIRTY_SURFACE",
                        "reason": "Còn vệt nước",
                        "note": "Kiểm tra dưới ánh sáng",
                        "reworkRequired": True,
                    }
                ],
            },
            "phase5-qc-reject",
        )
        self.assertEqual(reject.status_code, 200)
        self.task.refresh_from_db()
        self.task.room.refresh_from_db()
        first_qc.refresh_from_db()
        self.failed_item.refresh_from_db()
        self.good_item.refresh_from_db()
        self.assertEqual(self.task.status, HousekeepingTask.Status.QC_REJECTED)
        self.assertEqual(self.task.room.status, Room.Status.REWORK_REQUIRED)
        self.assertEqual(first_qc.checklist_snapshot, original_checklist_snapshot)
        self.assertEqual(first_qc.result_snapshot["failedItems"][0]["title"], "Lau gương")
        self.assertEqual(first_qc.photos.count(), 1)
        self.assertEqual(first_qc.failed_items.count(), 1)
        rework = self.task.rework_rounds.get(round_number=1)
        self.assertEqual(rework.status, ReworkRound.Status.PENDING)
        self.assertTrue(rework.failed_items_only)
        self.assertEqual(self.failed_item.status, TaskChecklistItem.Status.PENDING)
        self.assertEqual(self.good_item.status, TaskChecklistItem.Status.COMPLETED)
        self.assertEqual(self.task.progress_percent, 50)

        start = self.json_mutation(
            self.housekeeper_client,
            reverse("housekeeping:api-rework-start", kwargs={"task_id": self.task.id}),
            {"version": self.task.version},
            "phase5-rework-start",
        )
        self.assertEqual(start.status_code, 200)
        self.task.refresh_from_db()
        rework.refresh_from_db()
        self.assertEqual(rework.status, ReworkRound.Status.IN_PROGRESS)

        denied = self.json_mutation(
            self.housekeeper_client,
            reverse(
                "housekeeping:api-checklist-item",
                kwargs={"task_id": self.task.id, "item_id": self.good_item.id},
            ),
            {"version": self.task.version, "status": "COMPLETED", "value": True},
            "phase5-edit-good-item",
            method="patch",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.json()["code"], "TASK_ACCESS_DENIED")

        fixed = self.json_mutation(
            self.housekeeper_client,
            reverse(
                "housekeeping:api-checklist-item",
                kwargs={"task_id": self.task.id, "item_id": self.failed_item.id},
            ),
            {"version": self.task.version, "status": "COMPLETED", "value": True},
            "phase5-fix-failed-item",
            method="patch",
        )
        self.assertEqual(fixed.status_code, 200)
        version = fixed.json()["data"]["taskVersion"]
        complete = self.json_mutation(
            self.housekeeper_client,
            reverse("housekeeping:api-complete", kwargs={"task_id": self.task.id}),
            {
                "version": version,
                "confirmFinalInspection": True,
                "finalNote": "Đã lau lại gương",
            },
            "phase5-rework-complete",
        )
        self.assertEqual(complete.status_code, 200)
        self.task.refresh_from_db()
        rework.refresh_from_db()
        self.assertEqual(self.task.status, HousekeepingTask.Status.WAITING_QC)
        self.assertEqual(rework.status, ReworkRound.Status.SENT_TO_QC)
        second_qc = self.task.qc_rounds.get(round_number=2)
        self.assertNotEqual(first_qc.id, second_qc.id)

        approve = self.json_mutation(
            self.qc_client,
            reverse(
                "housekeeping:api-qc-round-review",
                kwargs={"task_id": self.task.id, "round_number": 2},
            ),
            {"version": self.task.version, "approved": True, "note": "Đạt"},
            "phase5-qc-approve",
        )
        self.assertEqual(approve.status_code, 200)
        self.task.refresh_from_db()
        self.task.room.refresh_from_db()
        rework.refresh_from_db()
        first_qc.refresh_from_db()
        second_qc.refresh_from_db()
        self.assertEqual(self.task.status, HousekeepingTask.Status.QC_APPROVED)
        self.assertEqual(self.task.room.status, Room.Status.READY)
        self.assertEqual(rework.status, ReworkRound.Status.COMPLETED)
        self.assertEqual(first_qc.status, QCTask.Status.REJECTED)
        self.assertEqual(first_qc.result_snapshot["reason"], "Gương còn vệt nước")
        self.assertEqual(second_qc.status, QCTask.Status.APPROVED)

        detail = self.housekeeper_client.get(
            reverse("housekeeping:api-task-detail", kwargs={"task_id": self.task.id})
        )
        self.assertEqual(detail.status_code, 200)
        data = detail.json()["data"]
        self.assertEqual(len(data["qcRounds"]), 2)
        self.assertEqual(data["qcRounds"][0]["failedItems"][0]["reasonCode"], "DIRTY_SURFACE")
        self.assertEqual(data["reworkRounds"][0]["status"], "COMPLETED")
