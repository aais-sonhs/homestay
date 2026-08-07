import json
from io import StringIO
from datetime import timedelta

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .models import (
    Branch,
    BranchMembership,
    HousekeepingTask,
    NotificationRecipient,
    OutboxEvent,
    Room,
    SLAEscalationEvent,
    SLAPolicy,
    Shift,
    SupplyRequest,
    TaskPause,
)
from .services import complete_task, create_supply_request, report_issue
from .sla import evaluate_task_sla


CONTEXT = {
    "ip": "127.0.0.1",
    "device_id": "phase6-device",
    "correlation_id": "phase6-test",
    "idempotency_key": "",
}


class SLANotificationDashboardTests(TestCase):
    def setUp(self):
        self.housekeeper = User.objects.create_user(
            username="phase6-housekeeper", password="Test@2026", role=User.Role.HOUSEKEEPING
        )
        self.lead = User.objects.create_user(
            username="phase6-lead", password="Test@2026", role=User.Role.HOUSEKEEPING
        )
        self.manager = User.objects.create_user(
            username="phase6-manager", password="Test@2026", role=User.Role.MANAGER
        )
        self.qc = User.objects.create_user(
            username="phase6-qc", password="Test@2026", role=User.Role.QC
        )
        self.warehouse = User.objects.create_user(
            username="phase6-warehouse", password="Test@2026", role=User.Role.WAREHOUSE
        )
        self.technician = User.objects.create_user(
            username="phase6-technician", password="Test@2026", role=User.Role.TECHNICIAN
        )
        self.branch = Branch.objects.create(
            code="PHASE6", name="Phase 6 Branch", owner=self.manager
        )
        memberships = (
            (self.housekeeper, BranchMembership.MembershipRole.HOUSEKEEPER),
            (self.lead, BranchMembership.MembershipRole.HOUSEKEEPING_LEAD),
            (self.manager, BranchMembership.MembershipRole.MANAGER),
            (self.qc, BranchMembership.MembershipRole.QC),
            (self.warehouse, BranchMembership.MembershipRole.WAREHOUSE),
            (self.technician, BranchMembership.MembershipRole.TECHNICIAN),
        )
        for user, role in memberships:
            BranchMembership.objects.create(
                user=user,
                branch=self.branch,
                membership_role=role,
            )
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="PHASE6-CURRENT",
            name="Ca Phase 6",
            starts_at=now - timedelta(hours=2),
            ends_at=now + timedelta(hours=8),
        )
        self.policy = SLAPolicy.objects.create(
            branch=self.branch,
            name="SLA mặc định",
            acceptance_minutes=5,
            start_minutes=15,
            completion_minutes=45,
            checkin_risk_buffer_minutes=15,
            escalation_minutes=[5, 15, 30],
        )
        self.counter = 0
        self.housekeeper_token = AccessToken.objects.create(user=self.housekeeper)
        self.manager_token = AccessToken.objects.create(user=self.manager)

    def make_task(
        self,
        *,
        status=HousekeepingTask.Status.IN_PROGRESS,
        assignee=None,
        due_at=None,
        acceptance_due_at=None,
        start_due_at=None,
        next_checkin_at=None,
        requires_qc=True,
    ):
        self.counter += 1
        now = timezone.now()
        room = Room.objects.create(
            branch=self.branch,
            code=f"P6-{self.counter:03}",
            name=f"Phòng Phase 6 {self.counter}",
            status=Room.Status.CLEANING,
        )
        owner = self.housekeeper if assignee is None else assignee
        return HousekeepingTask.objects.create(
            code=f"PHASE6-TASK-{self.counter:03}",
            branch=self.branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            priority=HousekeepingTask.Priority.NORMAL,
            status=status,
            assignee=owner,
            shift=self.shift,
            scheduled_start_at=now - timedelta(hours=1),
            acceptance_due_at=acceptance_due_at,
            start_due_at=start_due_at,
            due_at=due_at or now + timedelta(minutes=45),
            next_checkin_at=next_checkin_at,
            accepted_at=now - timedelta(minutes=55)
            if status not in {HousekeepingTask.Status.UNASSIGNED, HousekeepingTask.Status.PENDING_ACCEPTANCE}
            else None,
            started_at=now - timedelta(minutes=50)
            if status
            in {
                HousekeepingTask.Status.IN_PROGRESS,
                HousekeepingTask.Status.PAUSED,
                HousekeepingTask.Status.WAITING_SUPPORT,
            }
            else None,
            requires_qc=requires_qc,
        )

    def client_for(self, token):
        return Client(HTTP_AUTHORIZATION=f"Bearer {token.key}")

    def test_sla_breaches_escalate_once_to_each_role_and_mark_checkin_risk_urgent(self):
        now = timezone.now()
        overdue = now - timedelta(minutes=36)
        task = self.make_task(
            status=HousekeepingTask.Status.PENDING_ACCEPTANCE,
            due_at=overdue,
            acceptance_due_at=overdue,
            start_due_at=overdue,
            next_checkin_at=now + timedelta(minutes=10),
        )

        state = evaluate_task_sla(task, at=now)
        task.refresh_from_db()

        self.assertIsNotNone(state.acceptance_breached_at)
        self.assertIsNotNone(state.start_breached_at)
        self.assertIsNotNone(state.completion_breached_at)
        self.assertIsNotNone(state.checkin_risk_at)
        self.assertEqual(state.policy_id, self.policy.id)
        self.assertEqual(state.policy_snapshot["standardDurationMinutes"], 45)
        self.assertEqual(task.priority, HousekeepingTask.Priority.URGENT)
        self.assertEqual(
            list(task.sla_escalations.order_by("threshold_minutes").values_list("threshold_minutes", flat=True)),
            [5, 15, 30],
        )

        hk_thresholds = set(
            NotificationRecipient.objects.filter(
                user=self.housekeeper,
                notification__notification_type="SLA_ESCALATION",
            ).values_list("notification__payload__thresholdMinutes", flat=True)
        )
        lead_thresholds = set(
            NotificationRecipient.objects.filter(
                user=self.lead,
                notification__notification_type="SLA_ESCALATION",
            ).values_list("notification__payload__thresholdMinutes", flat=True)
        )
        manager_thresholds = set(
            NotificationRecipient.objects.filter(
                user=self.manager,
                notification__notification_type="SLA_ESCALATION",
            ).values_list("notification__payload__thresholdMinutes", flat=True)
        )
        self.assertEqual(hk_thresholds, {5})
        self.assertEqual(lead_thresholds, {15})
        self.assertEqual(manager_thresholds, {30})

        event_count = SLAEscalationEvent.objects.count()
        outbox_count = OutboxEvent.objects.count()
        notification_count = NotificationRecipient.objects.count()
        evaluate_task_sla(task, at=now + timedelta(minutes=2))
        self.assertEqual(SLAEscalationEvent.objects.count(), event_count)
        self.assertEqual(OutboxEvent.objects.count(), outbox_count)
        self.assertEqual(NotificationRecipient.objects.count(), notification_count)

    def test_near_due_notification_and_dashboard_duration_metrics(self):
        now = timezone.now()
        task = self.make_task(due_at=now + timedelta(minutes=4))
        pause = TaskPause.objects.create(
            task=task,
            previous_status=HousekeepingTask.Status.IN_PROGRESS,
            reason_code="WAITING_MANAGER",
            excluded_from_sla=True,
            paused_by=self.housekeeper,
        )
        TaskPause.objects.filter(pk=pause.pk).update(
            paused_at=now - timedelta(minutes=20),
            resumed_at=now - timedelta(minutes=10),
            resumed_by=self.housekeeper,
        )
        state = evaluate_task_sla(task, at=now)
        state.excluded_pause_seconds = 600
        state.save(update_fields=["excluded_pause_seconds", "updated_at"])

        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.housekeeper,
                notification__notification_type="SLA_NEAR_DUE",
                notification__payload__milestone="completion",
            ).exists()
        )

        response = self.client_for(self.manager_token).get(reverse("housekeeping:api-sla-dashboard"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        row = next(item for item in data["tasks"] if item["taskId"] == str(task.id))
        self.assertTrue(row["nearDue"])
        self.assertEqual(row["pauseSeconds"], 600)
        self.assertEqual(row["activeSeconds"], row["elapsedSeconds"] - 600)
        self.assertEqual(data["summary"]["nearDue"], 1)

        performance = self.client_for(self.manager_token).get(
            reverse("housekeeping:api-performance-dashboard")
        )
        self.assertEqual(performance.status_code, 200)
        employee_row = next(
            item
            for item in performance.json()["data"]["rows"]
            if item["employee"] and item["employee"]["id"] == str(self.housekeeper.id)
        )
        self.assertEqual(employee_row["taskCount"], 1)
        self.assertEqual(employee_row["reworkRoundCount"], 0)
        self.assertGreater(employee_row["averageActiveSeconds"], 0)

    def test_notification_list_read_is_scoped_and_idempotent(self):
        now = timezone.now()
        overdue = now - timedelta(minutes=20)
        task = self.make_task(
            status=HousekeepingTask.Status.PENDING_ACCEPTANCE,
            due_at=overdue,
            acceptance_due_at=overdue,
            start_due_at=overdue,
        )
        evaluate_task_sla(task, at=now)
        recipient = NotificationRecipient.objects.filter(user=self.housekeeper).first()
        client = self.client_for(self.housekeeper_token)

        listing = client.get(reverse("housekeeping:api-notification-list"), {"unread": "true"})
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(listing.json()["data"]["unreadCount"], 1)
        self.assertIn(
            str(recipient.id),
            {item["recipientId"] for item in listing.json()["data"]["items"]},
        )

        url = reverse("housekeeping:api-notification-read", kwargs={"recipient_id": recipient.id})
        first = client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase6-read-notification",
        )
        replay = client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase6-read-notification",
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.headers["Idempotent-Replayed"], "true")
        recipient.refresh_from_db()
        self.assertIsNotNone(recipient.read_at)

        denied = self.client_for(self.manager_token).post(
            url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="phase6-read-other-user",
        )
        self.assertEqual(denied.status_code, 404)

    def test_workflow_notifications_reach_qc_warehouse_and_technician(self):
        supply_task = self.make_task()
        supply, created = create_supply_request(
            self.housekeeper,
            supply_task.id,
            {
                "version": supply_task.version,
                "items": [{"inventoryItemId": "LINEN", "name": "Khăn", "quantity": 2}],
            },
            CONTEXT,
        )
        self.assertTrue(created)
        self.assertEqual(supply.status, SupplyRequest.Status.PENDING)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.warehouse,
                notification__notification_type="SUPPLY_REQUEST_CREATED",
            ).exists()
        )

        issue_task = self.make_task()
        issue, created = report_issue(
            self.housekeeper,
            issue_task.id,
            {
                "version": issue_task.version,
                "issueType": "AIR_CONDITIONER",
                "severity": HousekeepingTask.Priority.HIGH,
                "description": "Điều hòa không làm lạnh",
            },
            CONTEXT,
        )
        self.assertTrue(created)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.technician,
                notification__notification_type="ISSUE_REPORTED",
                notification__payload__issueId=str(issue.id),
            ).exists()
        )

        qc_task = self.make_task()
        completed = complete_task(
            self.housekeeper,
            qc_task.id,
            qc_task.version,
            True,
            "Đã kiểm tra cuối phòng",
            CONTEXT,
        )
        qc_round = completed.qc_rounds.get()
        self.assertEqual(completed.status, HousekeepingTask.Status.WAITING_QC)
        self.assertTrue(
            NotificationRecipient.objects.filter(
                user=self.qc,
                notification__notification_type="TASK_READY_FOR_QC",
                notification__payload__qcTaskId=str(qc_round.id),
            ).exists()
        )

    def test_periodic_sla_command_evaluates_a_selected_task(self):
        now = timezone.now()
        overdue = now - timedelta(minutes=16)
        task = self.make_task(
            status=HousekeepingTask.Status.PENDING_ACCEPTANCE,
            due_at=overdue,
            acceptance_due_at=overdue,
            start_due_at=overdue,
        )
        output = StringIO()

        call_command(
            "evaluate_housekeeping_sla",
            task_id=str(task.id),
            at=now.isoformat(),
            stdout=output,
        )

        task.refresh_from_db()
        self.assertIsNotNone(task.sla_state.last_evaluated_at)
        self.assertEqual(task.sla_escalations.count(), 2)
        self.assertIn("Đã đánh giá thời hạn cho 1 công việc buồng phòng.", output.getvalue())
