import hashlib
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User

from .idempotency import IdempotencyError, execute_idempotent
from .models import (
    Area,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    HousekeepingTask,
    HousekeepingTeam,
    Room,
    Shift,
    ShiftAssignment,
    TaskAssignment,
    TaskChecklistItem,
    TaskRoomVerification,
)
from .services import (
    HousekeepingError,
    accept_task,
    cancel_task,
    change_task_priority,
    complete_task,
    reassign_task,
    scoped_tasks,
    start_task,
)
from .state_machine import Action, InvalidTaskTransition, target_status


CONTEXT = {
    "ip": "127.0.0.1",
    "device_id": "policy-test-device",
    "correlation_id": "policy-test-request",
    "idempotency_key": "",
}


class PermissionAndStateMachineTests(TestCase):
    def setUp(self):
        self.hk_a = User.objects.create_user(username="policy-hk-a", password="Test@2026", role=User.Role.HOUSEKEEPING)
        self.hk_b = User.objects.create_user(username="policy-hk-b", password="Test@2026", role=User.Role.HOUSEKEEPING)
        self.lead = User.objects.create_user(username="policy-lead", password="Test@2026", role=User.Role.HOUSEKEEPING)
        self.manager = User.objects.create_user(username="policy-manager", password="Test@2026", role=User.Role.MANAGER)
        self.branch = Branch.objects.create(code="POLICY", name="Policy Branch")
        self.policy = BranchHousekeepingPolicy.objects.create(branch=self.branch)
        self.area_a = Area.objects.create(branch=self.branch, code="A", name="Khu A")
        self.area_b = Area.objects.create(branch=self.branch, code="B", name="Khu B")
        self.team_a = HousekeepingTeam.objects.create(branch=self.branch, code="TEAM-A", name="Đội A", leader=self.lead)
        self.team_b = HousekeepingTeam.objects.create(branch=self.branch, code="TEAM-B", name="Đội B")
        self.team_a.areas.add(self.area_a)
        self.team_b.areas.add(self.area_b)
        membership_a = BranchMembership.objects.create(
            user=self.hk_a,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
            team=self.team_a,
        )
        membership_a.areas.add(self.area_a)
        membership_b = BranchMembership.objects.create(
            user=self.hk_b,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
            team=self.team_a,
        )
        membership_b.areas.add(self.area_a)
        lead_membership = BranchMembership.objects.create(
            user=self.lead,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
            team=self.team_a,
            can_manage_team=True,
        )
        lead_membership.areas.add(self.area_a)
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        now = timezone.now()
        self.shift = Shift.objects.create(
            branch=self.branch,
            code="DAY",
            name="Ca ngày",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=7),
        )
        self.other_shift = Shift.objects.create(
            branch=self.branch,
            code="OTHER",
            name="Ca khác",
            starts_at=now - timedelta(minutes=30),
            ends_at=now + timedelta(hours=3),
        )
        self.counter = 0

    def make_task(
        self,
        *,
        area=None,
        team=None,
        room=None,
        status=HousekeepingTask.Status.UNASSIGNED,
        assignee=None,
        shift=None,
        requires_qc=True,
    ):
        self.counter += 1
        area = area or self.area_a
        team = team or self.team_a
        room = room or Room.objects.create(
            branch=self.branch,
            area_ref=area,
            area=area.name,
            code=f"P{self.counter:03}",
            name=f"Phòng {self.counter}",
            status=Room.Status.WAITING_CLEANING,
        )
        return HousekeepingTask.objects.create(
            code=f"POLICY-TASK-{self.counter:03}",
            branch=self.branch,
            room=room,
            area=area,
            team=team,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            priority=HousekeepingTask.Priority.NORMAL,
            status=status,
            assignee=assignee,
            shift=self.shift if shift is None else shift,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(minutes=45),
            requires_qc=requires_qc,
        )

    def test_selector_scopes_housekeeper_and_lead_by_area_and_team(self):
        own_area = self.make_task()
        other_area = self.make_task(area=self.area_b, team=self.team_b)
        hk_ids = set(scoped_tasks(self.hk_a).values_list("id", flat=True))
        lead_ids = set(scoped_tasks(self.lead).values_list("id", flat=True))
        manager_ids = set(scoped_tasks(self.manager).values_list("id", flat=True))

        self.assertIn(own_area.id, hk_ids)
        self.assertNotIn(other_area.id, hk_ids)
        self.assertIn(own_area.id, lead_ids)
        self.assertNotIn(other_area.id, lead_ids)
        self.assertEqual(manager_ids, {own_area.id, other_area.id})

    def test_explicit_roster_rejects_accepting_a_different_shift(self):
        ShiftAssignment.objects.create(user=self.hk_a, shift=self.shift, team=self.team_a)
        task = self.make_task(shift=self.other_shift)
        with self.assertRaises(HousekeepingError) as raised:
            accept_task(self.hk_a, task.id, task.version, CONTEXT)
        self.assertEqual(raised.exception.code, "USER_NOT_ON_SHIFT")

    def test_lead_reassigns_and_manager_changes_priority_then_cancels(self):
        task = self.make_task()
        task = reassign_task(
            self.lead,
            task.id,
            self.hk_b.id,
            task.version,
            CONTEXT,
            shift_id=self.shift.id,
            reason_code="BALANCE_WORKLOAD",
        )
        self.assertEqual(task.status, HousekeepingTask.Status.PENDING_ACCEPTANCE)
        self.assertEqual(task.assignee, self.hk_b)
        self.assertTrue(
            TaskAssignment.objects.filter(task=task, assignee=self.hk_b, is_current=True).exists()
        )

        task = change_task_priority(
            self.manager,
            task.id,
            task.version,
            HousekeepingTask.Priority.URGENT,
            "Khách sắp check-in",
            CONTEXT,
        )
        self.assertEqual(task.priority, HousekeepingTask.Priority.URGENT)
        task = cancel_task(self.manager, task.id, task.version, "Booking đã hủy", CONTEXT)
        self.assertEqual(task.status, HousekeepingTask.Status.CANCELLED)
        self.assertIsNotNone(task.cancelled_at)
        self.assertTrue(task.activity_logs.filter(action="TASK_CANCELLED").exists())

    def test_start_locks_room_against_another_active_task(self):
        shared_room = Room.objects.create(
            branch=self.branch,
            area_ref=self.area_a,
            area=self.area_a.name,
            code="SHARED",
            name="Phòng dùng chung",
            status=Room.Status.WAITING_CLEANING,
        )
        first = self.make_task(room=shared_room, status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk_a)
        second = self.make_task(room=shared_room, status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk_b)
        start_task(self.hk_a, first.id, first.version, CONTEXT)
        with self.assertRaises(HousekeepingError) as raised:
            start_task(self.hk_b, second.id, second.version, CONTEXT)
        self.assertEqual(raised.exception.code, "ROOM_ALREADY_IN_PROGRESS")

    def test_cancelling_active_task_recalculates_room_without_marking_ready(self):
        task = self.make_task(status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk_a)
        task = start_task(self.hk_a, task.id, task.version, CONTEXT)
        self.assertEqual(task.room.status, Room.Status.CLEANING)

        task = cancel_task(self.manager, task.id, task.version, "Booking đã hủy", CONTEXT)

        self.assertEqual(task.status, HousekeepingTask.Status.CANCELLED)
        self.assertEqual(task.room.status, Room.Status.WAITING_CLEANING)

    def test_qr_and_guest_consent_are_checked_before_start(self):
        self.policy.require_qr_verification = True
        self.policy.require_guest_consent = True
        self.policy.save(update_fields=["require_qr_verification", "require_guest_consent"])
        task = self.make_task(status=HousekeepingTask.Status.ACCEPTED, assignee=self.hk_a)
        task.room.qr_identifier_hash = hashlib.sha256(b"ROOM-POLICY-QR").hexdigest()
        task.room.is_guest_occupied = True
        task.room.save(update_fields=["qr_identifier_hash", "is_guest_occupied"])

        with self.assertRaises(HousekeepingError) as raised:
            start_task(
                self.hk_a,
                task.id,
                task.version,
                CONTEXT,
                {"method": "QR_CODE", "value": "WRONG", "guestConsentConfirmed": True},
            )
        self.assertEqual(raised.exception.code, "ROOM_VERIFICATION_FAILED")

        task = start_task(
            self.hk_a,
            task.id,
            task.version,
            CONTEXT,
            {"method": "QR_CODE", "value": "ROOM-POLICY-QR", "guestConsentConfirmed": True},
        )
        self.assertEqual(task.status, HousekeepingTask.Status.IN_PROGRESS)
        verification = TaskRoomVerification.objects.get(task=task)
        self.assertTrue(verification.successful)
        self.assertNotEqual(verification.submitted_value_hash, "ROOM-POLICY-QR")

    def test_completion_records_completed_then_waiting_qc(self):
        task = self.make_task(status=HousekeepingTask.Status.IN_PROGRESS, assignee=self.hk_a)
        TaskChecklistItem.objects.create(
            task=task,
            definition_key="final",
            title="Kiểm tra cuối",
            status=TaskChecklistItem.Status.COMPLETED,
            completed_by=self.hk_a,
            completed_at=timezone.now(),
        )
        task = complete_task(self.hk_a, task.id, task.version, True, "Đã xong", CONTEXT)
        history = list(task.status_history.order_by("changed_at", "id").values_list("to_status", flat=True))
        self.assertEqual(history[-2:], [HousekeepingTask.Status.COMPLETED, HousekeepingTask.Status.WAITING_QC])
        self.assertEqual(task.room.status, Room.Status.WAITING_QC)
        self.assertTrue(task.activity_logs.filter(action="TASK_COMPLETED").exists())
        self.assertTrue(task.activity_logs.filter(action="TASK_SENT_TO_QC").exists())

    def test_state_machine_rejects_undefined_transition(self):
        with self.assertRaises(InvalidTaskTransition):
            target_status(Action.ACCEPT, HousekeepingTask.Status.IN_PROGRESS)
        with self.assertRaises(InvalidTaskTransition):
            target_status(Action.REASSIGN, HousekeepingTask.Status.WAITING_QC)


class IdempotencyExecutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="idem-user", password="Test@2026")
        branch = Branch.objects.create(code="IDEM", name="Idempotency")
        room = Room.objects.create(branch=branch, code="I101", name="I101")
        self.task = HousekeepingTask.objects.create(
            code="IDEM-TASK",
            branch=branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(minutes=45),
        )

    def test_successful_mutation_is_executed_once_and_replayed(self):
        calls = []

        def mutation():
            calls.append("called")
            return {"taskId": str(self.task.id), "status": "ok"}, 2

        first, replayed_first, _ = execute_idempotent(
            user=self.user,
            task=self.task,
            idempotency_key="idem-001",
            operation="TEST_OPERATION",
            payload={"value": 1},
            base_version=1,
            mutation=mutation,
        )
        second, replayed_second, _ = execute_idempotent(
            user=self.user,
            task=self.task,
            idempotency_key="idem-001",
            operation="TEST_OPERATION",
            payload={"value": 1},
            base_version=1,
            mutation=mutation,
        )
        self.assertEqual(calls, ["called"])
        self.assertFalse(replayed_first)
        self.assertTrue(replayed_second)
        self.assertEqual(first, second)

    def test_reusing_key_with_another_payload_is_rejected(self):
        execute_idempotent(
            user=self.user,
            task=self.task,
            idempotency_key="idem-002",
            operation="TEST_OPERATION",
            payload={"value": 1},
            base_version=1,
            mutation=lambda: ({"ok": True}, 2),
        )
        with self.assertRaises(IdempotencyError) as raised:
            execute_idempotent(
                user=self.user,
                task=self.task,
                idempotency_key="idem-002",
                operation="TEST_OPERATION",
                payload={"value": 2},
                base_version=1,
                mutation=lambda: ({"ok": True}, 3),
            )
        self.assertEqual(raised.exception.code, "IDEMPOTENCY_KEY_REUSED")
