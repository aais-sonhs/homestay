import json
import tempfile
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .models import (
    Area,
    Branch,
    BranchMembership,
    HousekeepingTask,
    HousekeepingTeam,
    OfflineMutationReceipt,
    Room,
    Shift,
    ShiftAssignment,
    TaskChecklistItem,
)


class HousekeepingAPIContractTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.media_directory.cleanup)
        self.housekeeper = User.objects.create_user(
            username="api-housekeeper",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.manager = User.objects.create_user(
            username="api-manager",
            password="Test@2026",
            role=User.Role.MANAGER,
        )
        self.outsider = User.objects.create_user(
            username="api-outsider",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="API", name="API Branch", owner=self.manager
        )
        self.other_branch = Branch.objects.create(
            code="OTHER-API", name="Other API Branch", owner=self.outsider
        )
        self.area = Area.objects.create(branch=self.branch, code="A", name="Khu A")
        self.team = HousekeepingTeam.objects.create(branch=self.branch, code="TEAM", name="Đội API")
        self.team.areas.add(self.area)
        membership = BranchMembership.objects.create(
            user=self.housekeeper,
            branch=self.branch,
            team=self.team,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        membership.areas.add(self.area)
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(user=self.outsider, branch=self.other_branch)
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="CURRENT",
            name="Ca hiện tại",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=6),
        )
        self.other_shift = Shift.objects.create(
            branch=self.other_branch,
            code="CURRENT",
            name="Ca khác",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=6),
        )
        self.token = AccessToken.objects.create(user=self.housekeeper, label="API test")
        self.manager_token = AccessToken.objects.create(user=self.manager, label="Manager API test")
        self.counter = 0

    def make_task(
        self,
        *,
        branch=None,
        status=HousekeepingTask.Status.UNASSIGNED,
        assignee=None,
        priority=HousekeepingTask.Priority.NORMAL,
        due_delta=60,
    ):
        self.counter += 1
        branch = branch or self.branch
        is_main = branch == self.branch
        room = Room.objects.create(
            branch=branch,
            area_ref=self.area if is_main else None,
            area="Khu A" if is_main else "Khu khác",
            floor="2" if is_main else "1",
            room_type="DELUXE" if is_main else "STANDARD",
            code=f"API-{self.counter:03}",
            name=f"Phòng API {self.counter}",
            status=Room.Status.WAITING_CLEANING,
        )
        now = timezone.now()
        return HousekeepingTask.objects.create(
            code=f"API-TASK-{self.counter:03}",
            branch=branch,
            room=room,
            area=self.area if is_main else None,
            team=self.team if is_main else None,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            priority=priority,
            status=status,
            assignee=assignee,
            shift=self.shift if is_main else self.other_shift,
            scheduled_start_at=now,
            due_at=now + timedelta(minutes=due_delta),
            next_checkin_at=now + timedelta(minutes=45) if is_main else None,
        )

    def bearer_client(self, token=None, *, enforce_csrf_checks=False):
        client = Client(enforce_csrf_checks=enforce_csrf_checks)
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {(token or self.token).key}"
        return client

    def mutate(self, client, url, payload, key, *, method="post"):
        return getattr(client, method)(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key,
            HTTP_X_REQUEST_ID=f"request-{key}",
        )

    def test_bearer_list_is_scoped_and_touches_token(self):
        visible = self.make_task()
        visible.estimated_income = 125000
        visible.save(update_fields=["estimated_income"])
        hidden = self.make_task(branch=self.other_branch)

        response = self.bearer_client().get(reverse("housekeeping:api-task-list"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["data"][0]["id"], str(visible.id))
        self.assertEqual(payload["data"][0]["estimatedIncome"], 125000)
        self.assertNotIn(str(hidden.id), {item["id"] for item in payload["data"]})
        self.assertIn("correlationId", payload)
        self.token.refresh_from_db()
        self.assertIsNotNone(self.token.last_used_at)

    def test_invalid_or_revoked_bearer_returns_json_401(self):
        invalid = Client(HTTP_AUTHORIZATION="Bearer invalid")
        response = invalid.get(reverse("housekeeping:api-task-list"))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["code"], "TASK_ACCESS_DENIED")
        self.token.revoke()
        response = self.bearer_client().get(reverse("housekeeping:api-task-list"))
        self.assertEqual(response.status_code, 401)

    def test_token_login_refresh_rotation_and_logout(self):
        self.make_task()
        anonymous = Client(enforce_csrf_checks=True)
        login_response = anonymous.post(
            reverse("api-token-login"),
            data=json.dumps(
                {
                    "identifier": self.housekeeper.username,
                    "password": "Test@2026",
                    "deviceName": "Test phone",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(login_response.status_code, 201)
        login_data = login_response.json()["data"]
        access_key = login_data["accessToken"]
        refresh_key = login_data["refreshToken"]
        authenticated = Client(HTTP_AUTHORIZATION=f"Bearer {access_key}")
        self.assertEqual(authenticated.get(reverse("housekeeping:api-task-list")).status_code, 200)

        refresh_response = anonymous.post(
            reverse("api-token-refresh"),
            data=json.dumps({"refreshToken": refresh_key, "deviceName": "Test phone"}),
            content_type="application/json",
        )
        self.assertEqual(refresh_response.status_code, 201)
        refreshed = refresh_response.json()["data"]
        self.assertNotEqual(refreshed["refreshToken"], refresh_key)
        self.assertEqual(
            anonymous.post(
                reverse("api-token-refresh"),
                data=json.dumps({"refreshToken": refresh_key}),
                content_type="application/json",
            ).status_code,
            401,
        )

        refreshed_client = Client(HTTP_AUTHORIZATION=f"Bearer {refreshed['accessToken']}")
        logout_response = refreshed_client.post(
            reverse("api-token-logout"),
            data=json.dumps({"refreshToken": refreshed["refreshToken"]}),
            content_type="application/json",
        )
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(refreshed_client.get(reverse("housekeeping:api-task-list")).status_code, 401)

    def test_session_mutation_requires_csrf_but_bearer_does_not(self):
        session_task = self.make_task()
        session_client = Client(enforce_csrf_checks=True)
        session_client.force_login(self.housekeeper)
        response = self.mutate(
            session_client,
            reverse("housekeeping:api-accept", kwargs={"task_id": session_task.id}),
            {"version": session_task.version},
            "csrf-session",
        )
        self.assertEqual(response.status_code, 403)

        bearer_task = self.make_task()
        response = self.mutate(
            self.bearer_client(enforce_csrf_checks=True),
            reverse("housekeeping:api-accept", kwargs={"task_id": bearer_task.id}),
            {"version": bearer_task.version},
            "csrf-bearer",
        )
        self.assertEqual(response.status_code, 200)

    def test_accept_is_idempotent_and_rejects_key_reuse(self):
        task = self.make_task()
        client = self.bearer_client()
        url = reverse("housekeeping:api-accept", kwargs={"task_id": task.id})
        payload = {"version": task.version}

        first = self.mutate(client, url, payload, "accept-replay")
        second = self.mutate(client, url, payload, "accept-replay")
        reused = self.mutate(client, url, {"version": 99}, "accept-replay")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second["Idempotent-Replayed"], "true")
        self.assertEqual(first.json()["data"], second.json()["data"])
        self.assertEqual(reused.status_code, 409)
        self.assertEqual(reused.json()["code"], "IDEMPOTENCY_KEY_REUSED")
        self.assertEqual(OfflineMutationReceipt.objects.filter(user=self.housekeeper).count(), 1)

    def test_mutation_requires_version_and_idempotency_key(self):
        task = self.make_task()
        client = self.bearer_client()
        url = reverse("housekeeping:api-accept", kwargs={"task_id": task.id})
        missing_version = self.mutate(client, url, {}, "missing-version")
        missing_key = client.post(url, data=json.dumps({"version": 1}), content_type="application/json")
        self.assertEqual(missing_version.status_code, 409)
        self.assertEqual(missing_version.json()["code"], "TASK_VERSION_CONFLICT")
        self.assertEqual(missing_key.status_code, 400)
        self.assertEqual(missing_key.json()["code"], "IDEMPOTENCY_KEY_REQUIRED")

    def test_filters_stable_pagination_and_out_of_range_page(self):
        urgent = self.make_task(priority=HousekeepingTask.Priority.URGENT, due_delta=40)
        self.make_task(priority=HousekeepingTask.Priority.NORMAL, due_delta=90)
        client = self.bearer_client()
        url = reverse("housekeeping:api-task-list")

        response = client.get(
            url,
            {
                "branch": "API",
                "area": "A",
                "floor": "2",
                "roomType": "DELUXE",
                "priority": "URGENT",
                "checkinRisk": "true",
                "page": 1,
                "limit": 1,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["id"], str(urgent.id))
        self.assertEqual(response.json()["pagination"]["limit"], 1)

        empty = client.get(url, {"page": 999, "limit": 1})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["data"], [])
        self.assertEqual(empty.json()["pagination"]["page"], 999)

    def test_default_shift_uses_explicit_user_roster(self):
        assigned = self.make_task()
        parallel_shift = Shift.objects.create(
            branch=self.branch,
            code="PARALLEL",
            name="Ca song song",
            starts_at=timezone.now() - timedelta(hours=1),
            ends_at=timezone.now() + timedelta(hours=6),
        )
        hidden = self.make_task()
        hidden.shift = parallel_shift
        hidden.save(update_fields=["shift"])
        ShiftAssignment.objects.create(user=self.housekeeper, shift=self.shift, team=self.team)

        response = self.bearer_client().get(reverse("housekeeping:api-task-list"))

        ids = {item["id"] for item in response.json()["data"]}
        self.assertIn(str(assigned.id), ids)
        self.assertNotIn(str(hidden.id), ids)

        explicit = self.bearer_client().get(
            reverse("housekeeping:api-task-list"),
            {"shiftId": str(parallel_shift.id)},
        )
        self.assertEqual([item["id"] for item in explicit.json()["data"]], [str(hidden.id)])

    def test_detail_hides_other_branch_and_exposes_capabilities(self):
        visible = self.make_task()
        hidden = self.make_task(branch=self.other_branch)
        TaskChecklistItem.objects.create(
            task=visible,
            definition_key="detail",
            title="Checklist detail",
        )
        client = self.bearer_client()
        response = client.get(reverse("housekeeping:api-task-detail", kwargs={"task_id": visible.id}))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertTrue(data["capabilities"]["accept"])
        self.assertEqual(data["checklist"][0]["title"], "Checklist detail")
        denied = client.get(reverse("housekeeping:api-task-detail", kwargs={"task_id": hidden.id}))
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(denied.json()["code"], "TASK_NOT_FOUND")

    def test_other_branch_mutation_returns_branch_error(self):
        hidden = self.make_task(branch=self.other_branch)
        response = self.mutate(
            self.bearer_client(),
            reverse("housekeeping:api-accept", kwargs={"task_id": hidden.id}),
            {"version": hidden.version},
            "other-branch-accept",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "USER_BRANCH_NOT_ALLOWED")

    def test_execution_endpoints_keep_version_chain(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.housekeeper)
        item = TaskChecklistItem.objects.create(
            task=task,
            definition_key="api-chain",
            title="Checklist API chain",
            is_required=True,
        )
        client = self.bearer_client()
        checklist_response = self.mutate(
            client,
            reverse("housekeeping:api-checklist-item", kwargs={"task_id": task.id, "item_id": item.id}),
            {"version": task.version, "status": "COMPLETED", "value": True},
            "chain-checklist",
            method="patch",
        )
        self.assertEqual(checklist_response.status_code, 200)
        version = checklist_response.json()["data"]["taskVersion"]

        issue_response = self.mutate(
            client,
            reverse("housekeeping:api-issue", kwargs={"task_id": task.id}),
            {
                "version": version,
                "issueType": "COSMETIC",
                "severity": "LOW",
                "description": "Vết xước nhỏ",
                "blocksRoomReady": False,
                "clientRequestId": "chain-issue",
            },
            "chain-issue",
        )
        self.assertEqual(issue_response.status_code, 201)
        version = issue_response.json()["data"]["taskVersion"]

        supply_response = self.mutate(
            client,
            reverse("housekeeping:api-supply-request", kwargs={"task_id": task.id}),
            {
                "version": version,
                "items": [{"inventoryItemId": "WATER", "quantity": 1, "unit": "Chai"}],
                "blocksCompletion": False,
                "clientRequestId": "chain-supply",
            },
            "chain-supply",
        )
        self.assertEqual(supply_response.status_code, 201)
        self.assertEqual(supply_response.json()["data"]["taskStatus"], HousekeepingTask.Status.WAITING_SUPPORT)
        version = supply_response.json()["data"]["taskVersion"]

        resume_response = self.mutate(
            client,
            reverse("housekeeping:api-resume", kwargs={"task_id": task.id}),
            {"version": version},
            "chain-resume",
        )
        self.assertEqual(resume_response.status_code, 200)
        version = resume_response.json()["data"]["version"]
        complete_response = self.mutate(
            client,
            reverse("housekeeping:api-complete", kwargs={"task_id": task.id}),
            {"version": version, "confirmFinalInspection": True, "finalNote": "Hoàn tất"},
            "chain-complete",
        )
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["data"]["status"], HousekeepingTask.Status.WAITING_QC)
        detail_response = client.get(reverse("housekeeping:api-task-detail", kwargs={"task_id": task.id}))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(len(detail_response.json()["data"]["issues"]), 1)
        self.assertEqual(len(detail_response.json()["data"]["supplyRequests"]), 1)

    def test_media_upload_records_checksum_and_replays(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.housekeeper)
        url = reverse("housekeeping:api-media", kwargs={"task_id": task.id})
        client = self.bearer_client()
        image = SimpleUploadedFile("room.jpg", b"fake-jpeg-content", content_type="image/jpeg")
        first = client.post(
            url,
            {"version": task.version, "clientId": "media-001", "category": "AFTER", "image": image},
            HTTP_IDEMPOTENCY_KEY="media-upload",
        )
        self.assertEqual(first.status_code, 201)
        task.refresh_from_db()
        photo = task.photos.get()
        self.assertEqual(len(photo.checksum), 64)

        replay_image = SimpleUploadedFile("room.jpg", b"fake-jpeg-content", content_type="image/jpeg")
        replay = client.post(
            url,
            {"version": 1, "clientId": "media-001", "category": "AFTER", "image": replay_image},
            HTTP_IDEMPOTENCY_KEY="media-upload",
        )
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay["Idempotent-Replayed"], "true")
        self.assertEqual(task.photos.count(), 1)

    def test_manager_reassigns_changes_priority_and_cancels_via_api(self):
        task = self.make_task()
        client = self.bearer_client(self.manager_token)
        reassign_response = self.mutate(
            client,
            reverse("housekeeping:api-reassign", kwargs={"task_id": task.id}),
            {
                "version": task.version,
                "assigneeId": str(self.housekeeper.id),
                "shiftId": str(self.shift.id),
                "reasonCode": "BALANCE_WORKLOAD",
            },
            "manager-reassign",
        )
        self.assertEqual(reassign_response.status_code, 200)
        version = reassign_response.json()["data"]["version"]
        priority_response = self.mutate(
            client,
            reverse("housekeeping:api-priority", kwargs={"task_id": task.id}),
            {"version": version, "priority": "URGENT", "reason": "Khách sắp đến"},
            "manager-priority",
            method="patch",
        )
        self.assertEqual(priority_response.status_code, 200)
        version = priority_response.json()["data"]["version"]
        cancel_response = self.mutate(
            client,
            reverse("housekeeping:api-cancel", kwargs={"task_id": task.id}),
            {"version": version, "reason": "Booking hủy"},
            "manager-cancel",
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertEqual(cancel_response.json()["data"]["status"], HousekeepingTask.Status.CANCELLED)

    def test_manager_handover_preserves_progress_and_history(self):
        recipient = User.objects.create_user(
            username="api-handover-recipient",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        membership = BranchMembership.objects.create(
            user=recipient,
            branch=self.branch,
            team=self.team,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        membership.areas.add(self.area)
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.housekeeper)
        task.progress_percent = 65
        task.room.status = Room.Status.CLEANING
        task.save(update_fields=["progress_percent"])
        task.room.save(update_fields=["status"])

        response = self.mutate(
            self.bearer_client(self.manager_token),
            reverse("housekeeping:api-handover", kwargs={"task_id": task.id}),
            {
                "version": task.version,
                "recipientId": str(recipient.id),
                "shiftId": str(self.shift.id),
                "note": "Bàn giao cuối ca",
                "reconfirmRequiredItems": ["minibar"],
            },
            "manager-handover",
        )

        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.assignee, recipient)
        self.assertEqual(task.status, HousekeepingTask.Status.PENDING_ACCEPTANCE)
        self.assertEqual(task.progress_percent, 65)
        handover = task.handovers.get()
        self.assertEqual(handover.from_user, self.housekeeper)
        self.assertEqual(handover.to_user, recipient)
        self.assertEqual(handover.reconfirm_required_items, ["minibar"])
