import json
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .models import (
    Branch,
    BranchMembership,
    HousekeepingTask,
    OfflineMutationReceipt,
    Room,
    Shift,
    TaskChecklistItem,
)
from .services import completion_blockers


class OfflineClientSecurityContractTests(SimpleTestCase):
    """AC-27: no plaintext browser queue; Flutter secrets and cache are encrypted."""

    def test_web_template_has_no_business_local_storage_queue(self):
        template = (Path(settings.BASE_DIR) / "templates/housekeeping/task_detail.html").read_text()
        self.assertNotIn("localStorage", template)
        self.assertNotIn("bliss-housekeeping-checklist-queue", template)

    def test_flutter_client_uses_secure_tokens_sqlcipher_and_encrypted_photo_blob(self):
        root = Path(settings.BASE_DIR) / "housekeeping_app/lib/src"
        secure_store = (root / "security/secure_store.dart").read_text()
        database = (root / "storage/encrypted_database.dart").read_text()
        repository = (root / "offline/offline_repository.dart").read_text()
        self.assertIn("FlutterSecureStorage", secure_store)
        self.assertNotIn("SharedPreferences", secure_store)
        self.assertIn("password: password", database)
        self.assertIn("encrypted_blob BLOB NOT NULL", database)
        self.assertIn("Uint8List.fromList(bytes)", repository)


class OfflineSyncIntegrationTests(TestCase):
    """AC-27–AC-29 / TC-16–TC-17 backend sync contract."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="phase7-housekeeper",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.outsider = User.objects.create_user(
            username="phase7-outsider",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(code="PHASE7", name="Phase 7 Branch")
        self.other_branch = Branch.objects.create(code="PHASE7-OTHER", name="Phase 7 Other")
        BranchMembership.objects.create(user=self.user, branch=self.branch)
        BranchMembership.objects.create(user=self.outsider, branch=self.other_branch)
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="PHASE7-CURRENT",
            name="Ca Phase 7",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=6),
        )
        room = Room.objects.create(
            branch=self.branch,
            code="P7-101",
            name="Phòng P7-101",
            status=Room.Status.CLEANING,
        )
        self.task = HousekeepingTask.objects.create(
            code="PHASE7-TASK",
            branch=self.branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.user,
            shift=self.shift,
            scheduled_start_at=now - timedelta(minutes=30),
            due_at=now + timedelta(minutes=30),
            accepted_at=now - timedelta(minutes=25),
            started_at=now - timedelta(minutes=20),
        )
        self.item_one = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="offline-one",
            title="Offline item one",
            item_type=TaskChecklistItem.ItemType.CHECKBOX,
            sort_order=1,
        )
        self.item_two = TaskChecklistItem.objects.create(
            task=self.task,
            definition_key="offline-two",
            title="Offline item two",
            item_type=TaskChecklistItem.ItemType.CHECKBOX,
            sort_order=2,
        )
        self.token = AccessToken.objects.create(user=self.user)
        self.outsider_token = AccessToken.objects.create(user=self.outsider)
        self.client = Client(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")

    def post_batch(self, mutations):
        return self.client.post(
            reverse("housekeeping:api-sync-batch"),
            data=json.dumps({"mutations": mutations}),
            content_type="application/json",
            HTTP_X_DEVICE_ID="phase7-device",
        )

    def test_ordered_batch_syncs_checklist_once_and_replays_without_duplicates(self):
        mutations = [
            {
                "clientMutationId": "p7-check-one",
                "idempotencyKey": "p7-check-one",
                "operation": "UPDATE_CHECKLIST_ITEM",
                "taskId": str(self.task.id),
                "baseVersion": 1,
                "payload": {
                    "itemId": str(self.item_one.id),
                    "status": "COMPLETED",
                    "value": True,
                    "itemVersion": 1,
                },
            },
            {
                "clientMutationId": "p7-check-two",
                "idempotencyKey": "p7-check-two",
                "operation": "UPDATE_CHECKLIST_ITEM",
                "taskId": str(self.task.id),
                "baseVersion": 2,
                "dependsOn": ["p7-check-one"],
                "payload": {
                    "itemId": str(self.item_two.id),
                    "status": "COMPLETED",
                    "value": True,
                    "itemVersion": 1,
                },
            },
        ]

        first = self.post_batch(mutations)
        replay = self.post_batch(mutations)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["summary"]["synced"], 2)
        self.assertEqual([row["status"] for row in first.json()["data"]["results"]], ["SYNCED", "SYNCED"])
        self.assertTrue(all(row["replayed"] for row in replay.json()["data"]["results"]))
        self.task.refresh_from_db()
        self.item_one.refresh_from_db()
        self.item_two.refresh_from_db()
        self.assertEqual(self.task.version, 3)
        self.assertEqual(self.task.progress_percent, 100)
        self.assertEqual(self.item_one.update_version, 2)
        self.assertEqual(self.item_two.update_version, 2)
        self.assertEqual(
            OfflineMutationReceipt.objects.filter(status=OfflineMutationReceipt.Status.SUCCEEDED).count(),
            2,
        )

    def test_conflict_keeps_local_and_server_snapshots_and_blocks_dependents(self):
        HousekeepingTask.objects.filter(pk=self.task.id).update(version=2, note="Server mới hơn")
        mutations = [
            {
                "clientMutationId": "p7-note-conflict",
                "operation": "UPDATE_TASK_NOTE",
                "taskId": str(self.task.id),
                "baseVersion": 1,
                "baseSnapshot": {"version": 1, "note": "Ghi chú cũ"},
                "payload": {"note": "Ghi chú offline"},
            },
            {
                "clientMutationId": "p7-dependent-check",
                "operation": "UPDATE_CHECKLIST_ITEM",
                "taskId": str(self.task.id),
                "baseVersion": 2,
                "dependsOn": ["p7-note-conflict"],
                "payload": {
                    "itemId": str(self.item_one.id),
                    "status": "COMPLETED",
                    "value": True,
                },
            },
        ]

        response = self.post_batch(mutations)

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]["results"]
        self.assertEqual(rows[0]["status"], "CONFLICT")
        self.assertEqual(rows[1]["status"], "BLOCKED")
        conflict = rows[0]["conflict"]
        self.assertEqual(conflict["baseSnapshot"]["note"], "Ghi chú cũ")
        self.assertEqual(conflict["localOperation"]["payload"]["note"], "Ghi chú offline")
        self.assertEqual(conflict["serverSnapshot"]["version"], 2)
        self.assertEqual(conflict["serverSnapshot"]["note"], "Server mới hơn")
        self.item_one.refresh_from_db()
        self.assertEqual(self.item_one.status, TaskChecklistItem.Status.PENDING)
        self.assertFalse(
            OfflineMutationReceipt.objects.filter(client_mutation_id="p7-dependent-check").exists()
        )

        receipt_id = rows[0]["receiptId"]
        own = self.client.get(
            reverse("housekeeping:api-sync-conflict", kwargs={"receipt_id": receipt_id})
        )
        outsider = Client(HTTP_AUTHORIZATION=f"Bearer {self.outsider_token.key}").get(
            reverse("housekeeping:api-sync-conflict", kwargs={"receipt_id": receipt_id})
        )
        self.assertEqual(own.status_code, 200)
        self.assertEqual(outsider.status_code, 404)
        self.assertIn("PENDING_SYNC_EXISTS", {row["code"] for row in completion_blockers(self.task)})

    def test_user_can_discard_conflict_idempotently(self):
        HousekeepingTask.objects.filter(pk=self.task.id).update(version=2)
        response = self.post_batch(
            [
                {
                    "clientMutationId": "p7-discard-conflict",
                    "operation": "UPDATE_TASK_NOTE",
                    "taskId": str(self.task.id),
                    "baseVersion": 1,
                    "payload": {"note": "Không dùng nữa"},
                }
            ]
        )
        receipt_id = response.json()["data"]["results"][0]["receiptId"]
        url = reverse("housekeeping:api-sync-conflict-resolve", kwargs={"receipt_id": receipt_id})

        first = self.client.post(
            url,
            data=json.dumps({"action": "DISCARD_LOCAL"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-resolve-discard",
        )
        replay = self.client.post(
            url,
            data=json.dumps({"action": "DISCARD_LOCAL"}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-resolve-discard",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotent-Replayed"], "true")
        receipt = OfflineMutationReceipt.objects.get(pk=receipt_id)
        self.assertEqual(receipt.status, OfflineMutationReceipt.Status.DISCARDED)
        self.assertEqual(receipt.resolution, "DISCARD_LOCAL")
        self.assertNotIn("PENDING_SYNC_EXISTS", {row["code"] for row in completion_blockers(self.task)})

    def test_explicit_retry_uses_current_server_version_and_is_idempotent(self):
        HousekeepingTask.objects.filter(pk=self.task.id).update(version=2, note="Server note")
        response = self.post_batch(
            [
                {
                    "clientMutationId": "p7-retry-conflict",
                    "operation": "UPDATE_TASK_NOTE",
                    "taskId": str(self.task.id),
                    "baseVersion": 1,
                    "payload": {"note": "Local note được chọn"},
                }
            ]
        )
        receipt_id = response.json()["data"]["results"][0]["receiptId"]
        url = reverse("housekeeping:api-sync-conflict-resolve", kwargs={"receipt_id": receipt_id})
        payload = {
            "action": "RETRY_WITH_SERVER_VERSION",
            "newIdempotencyKey": "p7-retry-new-operation",
            "clientMutationId": "p7-retry-new-operation",
        }

        first = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-resolve-retry",
        )
        replay = self.client.post(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-resolve-retry",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["data"]["retry"]["status"], "SYNCED")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotent-Replayed"], "true")
        self.task.refresh_from_db()
        self.assertEqual(self.task.note, "Local note được chọn")
        self.assertEqual(self.task.version, 3)
        old_receipt = OfflineMutationReceipt.objects.get(pk=receipt_id)
        self.assertEqual(old_receipt.status, OfflineMutationReceipt.Status.DISCARDED)
        self.assertEqual(old_receipt.resolution, "RETRY_WITH_SERVER_VERSION")

    def test_direct_note_mutation_uses_same_idempotency_contract(self):
        url = reverse("housekeeping:api-task-note", kwargs={"task_id": self.task.id})
        payload = {"version": self.task.version, "note": "Ghi chú online/offline dùng chung"}

        first = self.client.patch(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-direct-note",
        )
        replay = self.client.patch(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-direct-note",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotent-Replayed"], "true")
        self.task.refresh_from_db()
        self.assertEqual(self.task.note, payload["note"])
        self.assertEqual(self.task.version, 2)

    def test_failed_mutation_does_not_abort_batch_and_can_be_discarded(self):
        response = self.post_batch(
            [
                {
                    "clientMutationId": "p7-failed-item",
                    "operation": "UPDATE_CHECKLIST_ITEM",
                    "taskId": str(self.task.id),
                    "baseVersion": 1,
                    "payload": {
                        "itemId": str(uuid.uuid4()),
                        "status": "COMPLETED",
                        "value": True,
                    },
                },
                {
                    "clientMutationId": "p7-independent-note",
                    "operation": "UPDATE_TASK_NOTE",
                    "taskId": str(self.task.id),
                    "baseVersion": 1,
                    "payload": {"note": "Mutation sau vẫn chạy"},
                },
            ]
        )

        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]["results"]
        self.assertEqual([row["status"] for row in rows], ["FAILED", "SYNCED"])
        self.task.refresh_from_db()
        self.assertEqual(self.task.note, "Mutation sau vẫn chạy")
        failed_receipt_id = rows[0]["receiptId"]
        self.assertIn("PENDING_SYNC_EXISTS", {row["code"] for row in completion_blockers(self.task)})

        discard = self.client.post(
            reverse(
                "housekeeping:api-sync-receipt-discard",
                kwargs={"receipt_id": failed_receipt_id},
            ),
            data=json.dumps({}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="p7-discard-failed-receipt",
        )

        self.assertEqual(discard.status_code, 200)
        self.assertEqual(discard.json()["data"]["status"], OfflineMutationReceipt.Status.DISCARDED)
        self.assertNotIn("PENDING_SYNC_EXISTS", {row["code"] for row in completion_blockers(self.task)})
