from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RoomOperationsInitialMigrationTests(TransactionTestCase):
    """Phase 2: open blocking issues become branch-scoped official blockers."""

    migrate_from = ("housekeeping", "0014_structured_booking_requests")
    migrate_to = ("room_operations", "0001_initial")
    accounts_state = ("accounts", "0010_add_sales_role")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(
            [("room_operations", None), self.migrate_from, self.accounts_state]
        )
        old_apps = executor.loader.project_state([self.migrate_from, self.accounts_state]).apps
        User = old_apps.get_model("accounts", "User")
        Branch = old_apps.get_model("housekeeping", "Branch")
        Room = old_apps.get_model("housekeeping", "Room")
        Task = old_apps.get_model("housekeeping", "HousekeepingTask")
        Issue = old_apps.get_model("housekeeping", "IssueTicket")

        owner = User.objects.create(username="stop-migration-owner", is_active=True)
        branch = Branch.objects.create(
            code="STOP-MIGRATION",
            name="Stop migration",
            owner_id=owner.id,
        )
        room = Room.objects.create(branch_id=branch.id, code="SM101", name="Phòng SM101")
        now = timezone.now()
        task = Task.objects.create(
            branch_id=branch.id,
            room_id=room.id,
            code="STOP-MIGRATION-TASK",
            task_type="CHECKOUT_CLEANING",
            status="WAITING_SUPPORT",
            scheduled_start_at=now,
            due_at=now + timedelta(hours=1),
        )
        open_issue = Issue.objects.create(
            task_id=task.id,
            room_id=room.id,
            reported_by_id=owner.id,
            issue_type="AIR_CONDITIONER",
            severity="HIGH",
            description="Máy lạnh không hoạt động",
            blocks_room_ready=True,
            status="OPEN",
        )
        resolved_issue = Issue.objects.create(
            task_id=task.id,
            room_id=room.id,
            reported_by_id=owner.id,
            issue_type="LIGHT",
            severity="NORMAL",
            description="Đèn đã thay xong",
            blocks_room_ready=True,
            status="RESOLVED",
            resolved_at=now,
        )
        self.branch_id = branch.id
        self.room_id = room.id
        self.open_issue_id = open_issue.id
        self.resolved_issue_id = resolved_issue.id

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to, self.accounts_state])
        self.apps = executor.loader.project_state([self.migrate_to, self.accounts_state]).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_only_open_blocking_issue_is_backfilled(self):
        Issue = self.apps.get_model("housekeeping", "IssueTicket")
        RoomBlocker = self.apps.get_model("room_operations", "RoomBlocker")
        self.assertTrue(
            Issue.objects.filter(
                pk=self.open_issue_id,
                blocks_room_ready=True,
                status="OPEN",
            ).exists()
        )
        blocker = RoomBlocker.objects.get(issue_id=self.open_issue_id)
        self.assertEqual(blocker.branch_id, self.branch_id)
        self.assertEqual(blocker.room_id, self.room_id)
        self.assertEqual(blocker.kind, "ISSUE")
        self.assertEqual(blocker.status, "ACTIVE")
        self.assertEqual(blocker.reason, "Máy lạnh không hoạt động")
        self.assertFalse(RoomBlocker.objects.filter(issue_id=self.resolved_issue_id).exists())
