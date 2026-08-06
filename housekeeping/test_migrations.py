from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class DomainFoundationMigrationTests(TransactionTestCase):
    """AC data safety: legacy 0001 rows are linked, not replaced or discarded."""

    migrate_from = ("housekeeping", "0001_initial")
    migrate_to = ("housekeeping", "0003_backfill_domain_foundation")
    accounts_state = ("accounts", "0001_initial")

    @property
    def app(self):
        return "housekeeping"

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from, self.accounts_state])
        old_apps = executor.loader.project_state([self.migrate_from, self.accounts_state]).apps
        self._create_legacy_rows(old_apps)

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.accounts_state])
        self.apps = executor.loader.project_state([self.migrate_to, self.accounts_state]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def _create_legacy_rows(self, apps):
        User = apps.get_model("accounts", "User")
        Branch = apps.get_model(self.app, "Branch")
        Membership = apps.get_model(self.app, "BranchMembership")
        Shift = apps.get_model(self.app, "Shift")
        Room = apps.get_model(self.app, "Room")
        Task = apps.get_model(self.app, "HousekeepingTask")
        ChecklistItem = apps.get_model(self.app, "TaskChecklistItem")
        TaskPhoto = apps.get_model(self.app, "TaskPhoto")
        SupplyRequest = apps.get_model(self.app, "SupplyRequest")
        IssueTicket = apps.get_model(self.app, "IssueTicket")
        QCTask = apps.get_model(self.app, "QCTask")

        self.user_id = User.objects.create(
            username="legacy-housekeeper",
            role="housekeeping",
            is_active=True,
        ).id
        branch = Branch.objects.create(code="LEGACY", name="Chi nhánh legacy")
        Membership.objects.create(
            user_id=self.user_id,
            branch_id=branch.id,
            area="Khu A",
            is_active=True,
        )
        now = timezone.now()
        shift = Shift.objects.create(
            branch_id=branch.id,
            code="DAY",
            name="Ca ngày",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=7),
        )
        room = Room.objects.create(
            branch_id=branch.id,
            code="A101",
            name="Phòng A101",
            floor="Tầng 1",
            area="Khu A",
            status="REWORK_REQUIRED",
        )
        task = Task.objects.create(
            code="LEGACY-TASK-001",
            branch_id=branch.id,
            room_id=room.id,
            booking_code="LEGACY-BOOKING-001",
            task_type="CHECKOUT_CLEANING",
            priority="HIGH",
            status="QC_REJECTED",
            assignee_id=self.user_id,
            shift_id=shift.id,
            checklist_version="legacy-v7",
            scheduled_start_at=now - timedelta(hours=1),
            due_at=now + timedelta(minutes=20),
            accepted_at=now - timedelta(minutes=55),
            started_at=now - timedelta(minutes=45),
            progress_percent=100,
            rework_count=1,
            created_by_id=self.user_id,
        )
        item = ChecklistItem.objects.create(
            task_id=task.id,
            definition_key="bathroom-mirror",
            group_name="Phòng tắm",
            title="Lau gương",
            item_type="CHECKBOX",
            is_required=True,
            requires_photo=True,
            status="COMPLETED",
            value=True,
            completed_by_id=self.user_id,
            completed_at=now - timedelta(minutes=10),
        )
        TaskPhoto.objects.create(
            task_id=task.id,
            checklist_item_id=item.id,
            uploaded_by_id=self.user_id,
            category="AFTER",
            image="housekeeping/legacy-after.jpg",
            synced=True,
            client_id="legacy-photo-001",
        )
        SupplyRequest.objects.create(
            task_id=task.id,
            branch_id=branch.id,
            requested_by_id=self.user_id,
            priority="HIGH",
            warehouse="Kho tầng 1",
            client_request_id="legacy-supply-001",
        )
        IssueTicket.objects.create(
            task_id=task.id,
            room_id=room.id,
            reported_by_id=self.user_id,
            issue_type="DEVICE_NOT_WORKING",
            severity="HIGH",
            description="Điều hòa hỏng",
            blocks_room_ready=True,
            client_request_id="legacy-issue-001",
        )
        QCTask.objects.create(
            task_id=task.id,
            round_number=1,
            status="REJECTED",
            reviewer_id=self.user_id,
            reason="Gương còn bẩn",
            note="Lau lại và chụp ảnh",
            reviewed_at=now - timedelta(minutes=5),
        )
        self.branch_id = branch.id
        self.room_id = room.id
        self.task_id = task.id
        self.item_id = item.id

    def test_legacy_rows_are_backfilled_into_domain_foundation(self):
        BranchPolicy = self.apps.get_model(self.app, "BranchHousekeepingPolicy")
        Area = self.apps.get_model(self.app, "Area")
        Membership = self.apps.get_model(self.app, "BranchMembership")
        Room = self.apps.get_model(self.app, "Room")
        Task = self.apps.get_model(self.app, "HousekeepingTask")
        Booking = self.apps.get_model(self.app, "Booking")
        ChecklistItem = self.apps.get_model(self.app, "TaskChecklistItem")
        TaskAssignment = self.apps.get_model(self.app, "TaskAssignment")
        ShiftAssignment = self.apps.get_model(self.app, "ShiftAssignment")
        TaskPhoto = self.apps.get_model(self.app, "TaskPhoto")
        SupplyRequest = self.apps.get_model(self.app, "SupplyRequest")
        IssueTicket = self.apps.get_model(self.app, "IssueTicket")
        QCTask = self.apps.get_model(self.app, "QCTask")
        ReworkRound = self.apps.get_model(self.app, "ReworkRound")
        TaskSLAState = self.apps.get_model(self.app, "TaskSLAState")

        self.assertTrue(BranchPolicy.objects.filter(branch_id=self.branch_id).exists())
        area = Area.objects.get(branch_id=self.branch_id, name="Khu A")
        room = Room.objects.get(pk=self.room_id)
        self.assertEqual(room.area_ref_id, area.id)

        membership = Membership.objects.get(user_id=self.user_id, branch_id=self.branch_id)
        self.assertEqual(membership.membership_role, "HOUSEKEEPER")
        self.assertIsNotNone(membership.team_id)
        self.assertTrue(membership.areas.filter(pk=area.id).exists())

        task = Task.objects.get(pk=self.task_id)
        self.assertEqual(task.code, "LEGACY-TASK-001")
        self.assertEqual(task.area_id, area.id)
        self.assertEqual(task.assignee_id, self.user_id)
        self.assertIsNotNone(task.booking_id)
        self.assertIsNotNone(task.checklist_template_version_id)
        self.assertEqual(task.current_rework_round, 1)
        self.assertTrue(Booking.objects.filter(pk=task.booking_id, code="LEGACY-BOOKING-001").exists())

        item = ChecklistItem.objects.get(pk=self.item_id)
        self.assertIsNotNone(item.definition_id)
        self.assertEqual(item.title, "Lau gương")
        self.assertTrue(TaskAssignment.objects.filter(task_id=task.id, assignee_id=self.user_id).exists())
        self.assertTrue(ShiftAssignment.objects.filter(user_id=self.user_id, shift_id=task.shift_id).exists())

        photo = TaskPhoto.objects.get(task_id=task.id)
        self.assertEqual(photo.room_id, room.id)
        self.assertIsNotNone(photo.captured_at)
        self.assertEqual(photo.sync_status, "SYNCED")

        supply = SupplyRequest.objects.get(task_id=task.id)
        self.assertIsNotNone(supply.destination_id)
        issue = IssueTicket.objects.get(task_id=task.id)
        self.assertEqual(issue.booking_id, task.booking_id)

        qc_round = QCTask.objects.get(task_id=task.id, round_number=1)
        self.assertEqual(qc_round.checklist_snapshot[0]["definition_key"], "bathroom-mirror")
        self.assertEqual(qc_round.result_snapshot["reason"], "Gương còn bẩn")
        self.assertTrue(ReworkRound.objects.filter(task_id=task.id, source_qc_round_id=qc_round.id).exists())
        self.assertTrue(TaskSLAState.objects.filter(task_id=task.id, legacy_backfill=True).exists())


class OfflineReceiptMigrationTests(TransactionTestCase):
    """AC-27–AC-29: migration 0005 preserves existing offline receipts."""

    migrate_from = ("housekeeping", "0004_execution_verification_policy")
    migrate_to = ("housekeeping", "0005_offline_sync_receipt_state")
    accounts_state = ("accounts", "0001_initial")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from, self.accounts_state])
        old_apps = executor.loader.project_state([self.migrate_from, self.accounts_state]).apps
        User = old_apps.get_model("accounts", "User")
        Receipt = old_apps.get_model("housekeeping", "OfflineMutationReceipt")
        user = User.objects.create(username="phase9-migration-user", is_active=True)
        self.receipt_id = Receipt.objects.create(
            user_id=user.id,
            idempotency_key="phase9-existing-receipt",
            operation="UPDATE_CHECKLIST_ITEM",
            payload_hash="a" * 64,
            request_payload={"value": True},
            response_payload={"progressPercent": 50},
            status="SUCCEEDED",
        ).id

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.accounts_state])
        self.apps = executor.loader.project_state([self.migrate_to, self.accounts_state]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_receipt_and_payload_survive_additive_sync_migration(self):
        Receipt = self.apps.get_model("housekeeping", "OfflineMutationReceipt")
        receipt = Receipt.objects.get(pk=self.receipt_id)

        self.assertEqual(receipt.status, "SUCCEEDED")
        self.assertEqual(receipt.request_payload, {"value": True})
        self.assertEqual(receipt.response_payload, {"progressPercent": 50})
        self.assertEqual(receipt.client_mutation_id, "")
        self.assertEqual(receipt.depends_on, [])
        self.assertEqual(receipt.conflict_payload, {})
        self.assertEqual(receipt.resolution, "")
        self.assertIsNone(receipt.resolved_at)
