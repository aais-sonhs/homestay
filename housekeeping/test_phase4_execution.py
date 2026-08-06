import hashlib
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
    OfflineMutationReceipt,
    Room,
    Shift,
    TaskChecklistItem,
    TaskPhoto,
    TaskRoomVerification,
    TaskSLAState,
)
from .services import (
    HousekeepingError,
    accept_checklist_failure,
    complete_task,
    completion_blockers,
    create_supply_request,
    report_issue,
    return_task,
    resume_task,
    start_task,
    update_checklist_item,
    upload_task_photo,
)


CONTEXT = {
    "ip": "127.0.0.1",
    "device_id": "phase-4-device",
    "correlation_id": "phase-4-checklist",
    "idempotency_key": "",
}


class TypedChecklistExecutionTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.housekeeper = User.objects.create_user(
            username="phase4-housekeeper",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.manager = User.objects.create_user(
            username="phase4-manager",
            password="Test@2026",
            role=User.Role.MANAGER,
        )
        self.warehouse = User.objects.create_user(
            username="phase4-warehouse",
            password="Test@2026",
            role=User.Role.WAREHOUSE,
        )
        self.technician = User.objects.create_user(
            username="phase4-technician",
            password="Test@2026",
            role=User.Role.TECHNICIAN,
        )
        self.branch = Branch.objects.create(code="PHASE4", name="Phase 4 Branch")
        self.policy = BranchHousekeepingPolicy.objects.create(branch=self.branch)
        BranchMembership.objects.create(user=self.housekeeper, branch=self.branch)
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.warehouse,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.WAREHOUSE,
        )
        BranchMembership.objects.create(
            user=self.technician,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.TECHNICIAN,
        )
        now = timezone.now()
        shift = Shift.objects.create(
            branch=self.branch,
            code="CURRENT",
            name="Ca hiện tại",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=5),
        )
        room = Room.objects.create(
            branch=self.branch,
            code="P401",
            name="Phòng P401",
            status=Room.Status.CLEANING,
        )
        self.task = HousekeepingTask.objects.create(
            code="PHASE4-TASK",
            branch=self.branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.housekeeper,
            shift=shift,
            scheduled_start_at=now,
            due_at=now + timedelta(minutes=45),
        )

    def item(self, key, item_type, *, options=None, rules=None):
        return TaskChecklistItem.objects.create(
            task=self.task,
            definition_key=key,
            title=key,
            item_type=item_type,
            options_snapshot=options or [],
            validation_snapshot=rules or {},
        )

    def update(self, item, value, *, status=TaskChecklistItem.Status.COMPLETED, **extra):
        item, self.task = update_checklist_item(
            self.housekeeper,
            self.task.id,
            item.id,
            {"version": self.task.version, "status": status, "value": value, **extra},
            CONTEXT,
        )
        return item

    def test_all_nine_item_types_validate_and_normalize(self):
        cases = [
            (self.item("checkbox", TaskChecklistItem.ItemType.CHECKBOX), True, True),
            (self.item("yes-no", TaskChecklistItem.ItemType.YES_NO), False, False),
            (
                self.item("number", TaskChecklistItem.ItemType.NUMBER, rules={"min": 1, "max": 4}),
                "3.5",
                3.5,
            ),
            (
                self.item("text", TaskChecklistItem.ItemType.TEXT, rules={"minLength": 3}),
                "  sạch sẽ  ",
                "sạch sẽ",
            ),
            (
                self.item("single", TaskChecklistItem.ItemType.SINGLE_SELECT, options=["A", "B"]),
                "B",
                "B",
            ),
            (
                self.item(
                    "multi",
                    TaskChecklistItem.ItemType.MULTI_SELECT,
                    options=["A", "B", "C"],
                    rules={"minSelections": 2},
                ),
                ["A", "C"],
                ["A", "C"],
            ),
            (self.item("device", TaskChecklistItem.ItemType.DEVICE_CHECK), True, True),
            (
                self.item(
                    "qr",
                    TaskChecklistItem.ItemType.QR_SCAN,
                    rules={"expectedHash": hashlib.sha256(b"ROOM-BARCODE").hexdigest()},
                ),
                "ROOM-BARCODE",
                "ROOM-BARCODE",
            ),
        ]
        photo_item = self.item(
            "photo",
            TaskChecklistItem.ItemType.PHOTO,
            rules={"requiredPhotoCount": 1},
        )
        TaskPhoto.objects.create(
            task=self.task,
            room=self.task.room,
            checklist_item=photo_item,
            uploaded_by=self.housekeeper,
            category=TaskPhoto.Category.AFTER,
            image="housekeeping/test-phase4.jpg",
        )
        cases.append((photo_item, None, None))

        for item, submitted, expected in cases:
            updated = self.update(item, submitted)
            self.assertEqual(updated.value, expected)
            self.assertEqual(updated.status, TaskChecklistItem.Status.COMPLETED)
            self.assertEqual(updated.completed_by, self.housekeeper)
            self.assertEqual(updated.update_version, 2)

        self.assertEqual(self.task.progress_percent, 100)

    def test_invalid_typed_value_does_not_change_task(self):
        item = self.item(
            "temperature",
            TaskChecklistItem.ItemType.NUMBER,
            rules={"min": 16, "max": 30},
        )
        with self.assertRaises(HousekeepingError) as raised:
            self.update(item, 45)
        self.assertEqual(raised.exception.code, "INVALID_CHECKLIST_VALUE")
        self.task.refresh_from_db()
        item.refresh_from_db()
        self.assertEqual(self.task.version, 1)
        self.assertEqual(item.status, TaskChecklistItem.Status.PENDING)

    def test_failed_item_requires_ticket_or_manager_accepted_reason(self):
        item = self.item("broken-lamp", TaskChecklistItem.ItemType.DEVICE_CHECK)
        item = self.update(
            item,
            False,
            status=TaskChecklistItem.Status.FAILED,
            failureReason="Đèn bàn không sáng",
        )
        with self.assertRaises(HousekeepingError) as raised:
            complete_task(self.housekeeper, self.task.id, self.task.version, True, "", CONTEXT)
        self.assertEqual(raised.exception.code, "FAILED_ITEM_UNRESOLVED")

        item, self.task = accept_checklist_failure(
            self.manager,
            self.task.id,
            item.id,
            self.task.version,
            "Cho phép gửi QC kèm ghi chú",
            CONTEXT,
        )
        self.assertEqual(item.failure_accepted_by, self.manager)
        completed = complete_task(
            self.housekeeper,
            self.task.id,
            self.task.version,
            True,
            "Đã kiểm tra phần còn lại",
            CONTEXT,
        )
        self.assertEqual(completed.status, HousekeepingTask.Status.WAITING_QC)

    def test_item_version_detects_same_task_parallel_edit(self):
        item = self.item("parallel", TaskChecklistItem.ItemType.CHECKBOX)
        with self.assertRaises(HousekeepingError) as raised:
            update_checklist_item(
                self.housekeeper,
                self.task.id,
                item.id,
                {
                    "version": self.task.version,
                    "itemVersion": 99,
                    "status": TaskChecklistItem.Status.COMPLETED,
                    "value": True,
                },
                CONTEXT,
            )
        self.assertEqual(raised.exception.code, "TASK_VERSION_CONFLICT")
        self.assertEqual(raised.exception.details["currentItemVersion"], 1)

    def test_combined_qr_gps_wifi_camera_and_guest_consent_verification(self):
        self.policy.require_qr_verification = True
        self.policy.require_gps_verification = True
        self.policy.require_wifi_verification = True
        self.policy.require_camera_verification = True
        self.policy.require_guest_consent = True
        self.policy.save(
            update_fields=[
                "require_qr_verification",
                "require_gps_verification",
                "require_wifi_verification",
                "require_camera_verification",
                "require_guest_consent",
            ]
        )
        self.task.status = HousekeepingTask.Status.ACCEPTED
        self.task.room.status = Room.Status.WAITING_CLEANING
        self.task.room.qr_identifier_hash = hashlib.sha256(b"PHASE4-ROOM-QR").hexdigest()
        self.task.room.latitude = "10.7750000"
        self.task.room.longitude = "106.7000000"
        self.task.room.verification_radius_meters = 100
        self.task.room.allowed_wifi_identifiers = ["BLISS-STAFF-5G"]
        self.task.room.is_guest_occupied = True
        self.task.save(update_fields=["status"])
        self.task.room.save(
            update_fields=[
                "status",
                "qr_identifier_hash",
                "latitude",
                "longitude",
                "verification_radius_meters",
                "allowed_wifi_identifiers",
                "is_guest_occupied",
            ]
        )
        before_photo, self.task, _ = upload_task_photo(
            self.housekeeper,
            self.task.id,
            SimpleUploadedFile("before.jpg", b"before-camera", content_type="image/jpeg"),
            {
                "version": self.task.version,
                "category": TaskPhoto.Category.BEFORE,
                "source": TaskPhoto.Source.CAMERA,
                "clientId": "before-verification",
            },
            CONTEXT,
        )
        verification = {
            "qrCode": "PHASE4-ROOM-QR",
            "location": {
                "latitude": 10.77501,
                "longitude": 106.70001,
                "accuracyMeters": 8,
            },
            "wifiIdentifier": "BLISS-STAFF-5G",
            "cameraPhotoId": str(before_photo.id),
        }
        with self.assertRaises(HousekeepingError) as raised:
            start_task(self.housekeeper, self.task.id, self.task.version, CONTEXT, verification)
        self.assertEqual(raised.exception.code, "GUEST_CONSENT_REQUIRED")
        self.assertEqual(TaskRoomVerification.objects.filter(task=self.task).count(), 0)

        token = AccessToken.objects.create(user=self.housekeeper)
        client = Client(HTTP_AUTHORIZATION=f"Bearer {token.key}")
        response = client.post(
            reverse("housekeeping:api-start", kwargs={"task_id": self.task.id}),
            data=json.dumps(
                {
                    "version": self.task.version,
                    "roomVerification": {"qrCode": "PHASE4-ROOM-QR"},
                    "location": verification["location"],
                    "wifiIdentifier": verification["wifiIdentifier"],
                    "cameraPhotoId": verification["cameraPhotoId"],
                    "guestConsentConfirmed": True,
                    "guestConsentNote": "Khách đồng ý cho vào dọn lúc 10:00",
                }
            ),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-combined-start",
        )
        self.assertEqual(response.status_code, 200)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, HousekeepingTask.Status.IN_PROGRESS)
        records = self.task.room_verifications.all()
        self.assertEqual(records.count(), 4)
        self.assertEqual(
            set(records.values_list("method", flat=True)),
            {
                TaskRoomVerification.Method.QR_CODE,
                TaskRoomVerification.Method.GPS,
                TaskRoomVerification.Method.WIFI,
                TaskRoomVerification.Method.CAMERA,
            },
        )
        self.assertTrue(all(record.guest_consent_confirmed for record in records))

    def test_evidence_camera_policy_and_media_metadata(self):
        self.policy.require_direct_camera_for_evidence = True
        self.policy.save(update_fields=["require_direct_camera_for_evidence"])
        with self.assertRaises(HousekeepingError) as raised:
            upload_task_photo(
                self.housekeeper,
                self.task.id,
                SimpleUploadedFile("gallery.jpg", b"gallery", content_type="image/jpeg"),
                {
                    "version": self.task.version,
                    "category": TaskPhoto.Category.EVIDENCE,
                    "source": TaskPhoto.Source.GALLERY,
                },
                CONTEXT,
            )
        self.assertEqual(raised.exception.code, "REQUIRED_PHOTO_MISSING")

        photo, self.task, created = upload_task_photo(
            self.housekeeper,
            self.task.id,
            SimpleUploadedFile("camera.jpg", b"camera", content_type="image/jpeg"),
            {
                "version": self.task.version,
                "category": TaskPhoto.Category.EVIDENCE,
                "source": TaskPhoto.Source.CAMERA,
                "capturedAt": "2026-08-05T09:30:00+07:00",
                "latitude": "10.775",
                "longitude": "106.700",
                "accuracyMeters": "12.5",
                "metadata": {"width": 1280, "height": 960},
            },
            CONTEXT,
        )
        self.assertTrue(created)
        self.assertEqual(photo.latitude, "10.775")
        self.assertEqual(photo.metadata["width"], 1280)
        self.assertEqual(self.task.updated_by, self.housekeeper)
        self.assertIsNotNone(self.task.last_progress_at)

    def test_supply_and_issue_queues_resolve_blockers_and_accumulate_sla_pause(self):
        TaskSLAState.objects.create(task=self.task)
        supply, _ = create_supply_request(
            self.housekeeper,
            self.task.id,
            {
                "version": self.task.version,
                "items": [{"inventoryItemId": "TOWEL", "quantity": 2, "unit": "Cái"}],
                "clientRequestId": "phase4-supply",
            },
            CONTEXT,
        )
        self.task.refresh_from_db()
        self.task.pauses.update(paused_at=timezone.now() - timedelta(minutes=2))
        issue, _ = report_issue(
            self.housekeeper,
            self.task.id,
            {
                "version": self.task.version,
                "issueType": "DOOR_LOCK",
                "severity": "URGENT",
                "description": "Khóa cửa không hoạt động",
                "blocksRoomReady": True,
                "clientRequestId": "phase4-issue",
            },
            CONTEXT,
        )

        warehouse_token = AccessToken.objects.create(user=self.warehouse)
        warehouse_client = Client(HTTP_AUTHORIZATION=f"Bearer {warehouse_token.key}")
        queue = warehouse_client.get(reverse("housekeeping:api-supply-queue"))
        self.assertEqual(queue.status_code, 200)
        self.assertEqual(queue.json()["data"][0]["id"], str(supply.id))
        acknowledged = warehouse_client.patch(
            reverse("housekeeping:api-supply-queue-update", kwargs={"request_id": supply.id}),
            data=json.dumps({"version": 1, "status": "ACKNOWLEDGED"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-supply-ack",
        )
        self.assertEqual(acknowledged.status_code, 200)
        fulfilled = warehouse_client.patch(
            reverse("housekeeping:api-supply-queue-update", kwargs={"request_id": supply.id}),
            data=json.dumps({"version": 2, "status": "FULFILLED", "note": "Đã giao đủ"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-supply-fulfilled",
        )
        self.assertEqual(fulfilled.status_code, 200)

        technician_token = AccessToken.objects.create(user=self.technician)
        technician_client = Client(HTTP_AUTHORIZATION=f"Bearer {technician_token.key}")
        issue_queue = technician_client.get(reverse("housekeeping:api-issue-queue"))
        self.assertEqual(issue_queue.status_code, 200)
        self.assertEqual(issue_queue.json()["data"][0]["id"], str(issue.id))
        assigned = technician_client.patch(
            reverse("housekeeping:api-issue-queue-update", kwargs={"issue_id": issue.id}),
            data=json.dumps(
                {
                    "version": 1,
                    "status": "ASSIGNED",
                    "assignedToId": str(self.technician.id),
                }
            ),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-issue-assign",
        )
        self.assertEqual(assigned.status_code, 200)
        in_progress = technician_client.patch(
            reverse("housekeeping:api-issue-queue-update", kwargs={"issue_id": issue.id}),
            data=json.dumps({"version": 2, "status": "IN_PROGRESS"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-issue-progress",
        )
        self.assertEqual(in_progress.status_code, 200)
        resolved = technician_client.patch(
            reverse("housekeeping:api-issue-queue-update", kwargs={"issue_id": issue.id}),
            data=json.dumps({"version": 3, "status": "RESOLVED", "note": "Đã thay khóa"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase4-issue-resolve",
        )
        self.assertEqual(resolved.status_code, 200)

        self.task.refresh_from_db()
        self.task = resume_task(
            self.housekeeper,
            self.task.id,
            self.task.version,
            CONTEXT,
        )
        self.assertEqual(self.task.status, HousekeepingTask.Status.IN_PROGRESS)
        sla = TaskSLAState.objects.get(task=self.task)
        self.assertGreaterEqual(sla.excluded_pause_seconds, 119)

    def test_completion_summary_and_complete_share_pending_sync_policy(self):
        OfflineMutationReceipt.objects.create(
            user=self.housekeeper,
            task=self.task,
            idempotency_key="pending-offline-change",
            operation="UPDATE_CHECKLIST_ITEM",
            payload_hash="a" * 64,
            status=OfflineMutationReceipt.Status.RECEIVED,
        )
        token = AccessToken.objects.create(user=self.housekeeper)
        client = Client(HTTP_AUTHORIZATION=f"Bearer {token.key}")
        summary = client.get(
            reverse("housekeeping:api-completion-summary", kwargs={"task_id": self.task.id})
        )
        self.assertEqual(summary.status_code, 200)
        self.assertFalse(summary.json()["data"]["canComplete"])
        self.assertIn(
            "PENDING_SYNC_EXISTS",
            {blocker["code"] for blocker in summary.json()["data"]["blockers"]},
        )
        with self.assertRaises(HousekeepingError) as raised:
            complete_task(
                self.housekeeper,
                self.task.id,
                self.task.version,
                True,
                "",
                CONTEXT,
            )
        self.assertEqual(raised.exception.code, "PENDING_SYNC_EXISTS")

        self.policy.block_completion_with_pending_sync = False
        self.policy.save(update_fields=["block_completion_with_pending_sync"])
        completed = complete_task(
            self.housekeeper,
            self.task.id,
            self.task.version,
            True,
            "",
            CONTEXT,
        )
        self.assertEqual(completed.status, HousekeepingTask.Status.WAITING_QC)

    def test_required_photo_count_only_accepts_synced_media(self):
        item = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="two-photos",
            title="Hai ảnh bằng chứng",
            item_type=TaskChecklistItem.ItemType.PHOTO,
            status=TaskChecklistItem.Status.COMPLETED,
            completed_by=self.housekeeper,
            completed_at=timezone.now(),
            validation_snapshot={"requiredPhotoCount": 2},
        )
        first = TaskPhoto.objects.create(
            task=self.task,
            room=self.task.room,
            checklist_item=item,
            uploaded_by=self.housekeeper,
            category=TaskPhoto.Category.EVIDENCE,
            image="housekeeping/first.jpg",
            sync_status=TaskPhoto.SyncStatus.SYNCED,
        )
        second = TaskPhoto.objects.create(
            task=self.task,
            room=self.task.room,
            checklist_item=item,
            uploaded_by=self.housekeeper,
            category=TaskPhoto.Category.EVIDENCE,
            image="housekeeping/second.jpg",
            sync_status=TaskPhoto.SyncStatus.PENDING,
            synced=False,
        )
        blockers = completion_blockers(self.task)
        required = next(blocker for blocker in blockers if blocker["code"] == "REQUIRED_PHOTO_MISSING")
        self.assertEqual(required["details"]["items"][0]["requiredCount"], 2)
        self.assertEqual(required["details"]["items"][0]["syncedCount"], 1)
        self.assertTrue(any(blocker["code"] == "PENDING_SYNC_EXISTS" for blocker in blockers))

        second.sync_status = TaskPhoto.SyncStatus.SYNCED
        second.synced = True
        second.save(update_fields=["sync_status", "synced"])
        blockers = completion_blockers(self.task)
        self.assertFalse(any(blocker["code"] == "REQUIRED_PHOTO_MISSING" for blocker in blockers))
        self.assertFalse(any(blocker["code"] == "PENDING_SYNC_EXISTS" for blocker in blockers))
        self.assertIsNotNone(first.id)

    def test_return_after_start_is_policy_controlled_and_preserves_progress(self):
        self.task.progress_percent = 50
        self.task.save(update_fields=["progress_percent"])
        with self.assertRaises(HousekeepingError) as raised:
            return_task(
                self.housekeeper,
                self.task.id,
                self.task.version,
                "HIGHER_PRIORITY_TASK",
                "Cần chuyển sang phòng gấp",
                CONTEXT,
            )
        self.assertEqual(raised.exception.code, "TASK_INVALID_STATUS")

        self.policy.allow_return_after_start = True
        self.policy.save(update_fields=["allow_return_after_start"])
        returned = return_task(
            self.housekeeper,
            self.task.id,
            self.task.version,
            "HIGHER_PRIORITY_TASK",
            "Cần chuyển sang phòng gấp",
            CONTEXT,
        )
        self.assertEqual(returned.status, HousekeepingTask.Status.UNASSIGNED)
        self.assertIsNone(returned.assignee)
        self.assertEqual(returned.progress_percent, 50)
        self.assertNotEqual(returned.room.status, Room.Status.READY)
        log = returned.activity_logs.filter(action="TASK_RETURNED").latest("created_at")
        self.assertTrue(log.changes["returnedAfterStart"])
