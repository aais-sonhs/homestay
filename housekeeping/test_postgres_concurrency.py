from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from accounts.models import User
from reservations.services import BookingOperationError, create_booking, update_booking
from room_operations.models import RoomBlocker, RoomStopSell
from room_operations.services import (
    RoomOperationsError,
    confirm_room_reopen,
    create_room_stop_sell,
    request_room_reopen,
)

from .models import Branch, BranchMembership, HousekeepingTask, Room, Shift
from .services import HousekeepingError, accept_task, start_task
from .sla import evaluate_task_sla


class PostgreSQLAcceptConcurrencyTests(TransactionTestCase):
    """AC-06/AC-11, TC-04/TC-06: real PostgreSQL row-lock races."""

    reset_sequences = True

    def setUp(self):
        self.users = [
            User.objects.create_user(username=f"concurrent-hk-{index}", password="Test@2026", role=User.Role.HOUSEKEEPING)
            for index in range(2)
        ]
        branch = Branch.objects.create(
            code="CONCURRENT", name="Concurrent Branch", owner=self.users[0]
        )
        for user in self.users:
            BranchMembership.objects.create(user=user, branch=branch)
        now = timezone.now()
        shift = Shift.objects.create(
            branch=branch,
            code="CURRENT",
            name="Ca hiện tại",
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(hours=4),
        )
        room = Room.objects.create(
            branch=branch,
            code="C101",
            name="Phòng C101",
            status=Room.Status.WAITING_CLEANING,
        )
        self.task = HousekeepingTask.objects.create(
            code="CONCURRENT-TASK",
            branch=branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.UNASSIGNED,
            shift=shift,
            scheduled_start_at=now,
            due_at=now + timedelta(minutes=45),
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_of_two_simultaneous_accepts_succeeds(self):
        barrier = Barrier(2)

        def attempt(user_id):
            close_old_connections()
            user = User.objects.get(pk=user_id)
            barrier.wait(timeout=5)
            try:
                task = accept_task(
                    user,
                    self.task.id,
                    1,
                    {
                        "ip": "127.0.0.1",
                        "device_id": f"thread-{user_id}",
                        "correlation_id": f"accept-{user_id}",
                        "idempotency_key": "",
                    },
                )
                return "success", user_id, task.version
            except HousekeepingError as error:
                return error.code, user_id, None
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, [user.id for user in self.users]))

        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result[0] == "TASK_ALREADY_ASSIGNED" for result in results), 1)
        self.task.refresh_from_db()
        successful_user_id = next(result[1] for result in results if result[0] == "success")
        self.assertEqual(self.task.assignee_id, successful_user_id)

    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_of_two_tasks_can_start_in_the_same_room(self):
        self.task.status = HousekeepingTask.Status.ACCEPTED
        self.task.assignee = self.users[0]
        self.task.save(update_fields=["status", "assignee"])
        other_task = HousekeepingTask.objects.create(
            code="CONCURRENT-ROOM-TASK",
            branch=self.task.branch,
            room=self.task.room,
            task_type=HousekeepingTask.TaskType.DEEP_CLEANING,
            status=HousekeepingTask.Status.ACCEPTED,
            assignee=self.users[1],
            shift=self.task.shift,
            scheduled_start_at=self.task.scheduled_start_at,
            due_at=self.task.due_at,
        )
        barrier = Barrier(2)

        def attempt(user_id, task_id):
            close_old_connections()
            user = User.objects.get(pk=user_id)
            barrier.wait(timeout=5)
            try:
                started = start_task(
                    user,
                    task_id,
                    1,
                    {
                        "ip": "127.0.0.1",
                        "device_id": f"room-thread-{user_id}",
                        "correlation_id": f"start-{task_id}",
                        "idempotency_key": "",
                    },
                )
                return "success", started.id
            except HousekeepingError as error:
                return error.code, task_id
            finally:
                close_old_connections()

        attempts = [
            (self.users[0].id, self.task.id),
            (self.users[1].id, other_task.id),
        ]
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda args: attempt(*args), attempts))

        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result[0] == "ROOM_ALREADY_IN_PROGRESS" for result in results), 1)
        self.assertEqual(
            HousekeepingTask.objects.filter(
                room=self.task.room,
                status=HousekeepingTask.Status.IN_PROGRESS,
            ).count(),
            1,
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_sla_evaluation_locks_only_task_when_assignee_is_null(self):
        self.assertIsNone(self.task.assignee_id)

        state = evaluate_task_sla(self.task, at=timezone.now())

        self.assertEqual(state.task_id, self.task.id)
        self.assertIsNotNone(state.last_evaluated_at)


class PostgreSQLBookingConcurrencyTests(TransactionTestCase):
    """Phase 1: the booking version lock serializes two simultaneous reschedules."""

    reset_sequences = True

    def setUp(self):
        self.sales = User.objects.create_user(
            username="concurrent-booking-sales",
            password="Test@2026",
            role=User.Role.SALES,
        )
        branch = Branch.objects.create(
            code="BOOKING-CONCURRENT",
            name="Booking Concurrent Branch",
            owner=self.sales,
        )
        BranchMembership.objects.create(
            user=self.sales,
            branch=branch,
            membership_role=BranchMembership.MembershipRole.SALES,
        )
        self.rooms = [
            Room.objects.create(
                branch=branch,
                code=f"BC{index}",
                name=f"Phòng BC{index}",
                status=Room.Status.READY,
            )
            for index in range(3)
        ]
        now = timezone.localtime().replace(second=0, microsecond=0)
        self.checkin_at = now + timedelta(days=3)
        self.checkout_at = now + timedelta(days=5)
        self.booking, _ = create_booking(
            self.sales,
            {
                "branch": branch,
                "room": self.rooms[0],
                "code": "CONCURRENT-BOOKING",
                "guest_name": "Khách concurrency",
                "guest_phone": "0900000000",
                "guest_count": 2,
                "checkin_at": self.checkin_at,
                "checkout_at": self.checkout_at,
                "special_requests": "",
            },
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_of_two_simultaneous_reschedules_succeeds(self):
        barrier = Barrier(2)

        def attempt(room_id):
            close_old_connections()
            user = User.objects.get(pk=self.sales.id)
            room = Room.objects.get(pk=room_id)
            barrier.wait(timeout=5)
            try:
                updated, _ = update_booking(
                    user,
                    self.booking.id,
                    {
                        "room": room,
                        "guest_name": self.booking.guest_name,
                        "guest_phone": self.booking.guest_phone,
                        "guest_count": self.booking.guest_count,
                        "checkin_at": self.checkin_at,
                        "checkout_at": self.checkout_at,
                        "special_requests": "",
                    },
                    1,
                )
                return "success", updated.room_id
            except BookingOperationError:
                return "conflict", room_id
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, [self.rooms[1].id, self.rooms[2].id]))

        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result[0] == "conflict" for result in results), 1)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.version, 2)
        self.assertIn(self.booking.room_id, {self.rooms[1].id, self.rooms[2].id})

    @skipUnlessDBFeature("has_select_for_update")
    def test_only_one_of_two_overlapping_stop_sells_is_created(self):
        barrier = Barrier(2)
        starts_at = self.checkin_at + timedelta(days=10)
        planned_end_at = starts_at + timedelta(days=1)

        def attempt(marker):
            close_old_connections()
            user = User.objects.get(pk=self.sales.id)
            room = Room.objects.get(pk=self.rooms[1].id)
            branch = room.branch
            barrier.wait(timeout=5)
            try:
                stop_sell, _ = create_room_stop_sell(
                    user,
                    {
                        "branch": branch,
                        "room": room,
                        "blocker": None,
                        "reason_code": RoomStopSell.ReasonCode.MAINTENANCE,
                        "reason": f"Race stop sell {marker}",
                        "starts_at": starts_at,
                        "planned_end_at": planned_end_at,
                    },
                )
                return "success", stop_sell.id
            except RoomOperationsError as error:
                return error.code, marker
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, ["A", "B"]))

        self.assertEqual(sum(result[0] == "success" for result in results), 1)
        self.assertEqual(sum(result[0] == "STOP_SELL_OVERLAP" for result in results), 1)
        self.assertEqual(
            RoomStopSell.objects.filter(
                room=self.rooms[1],
                status=RoomStopSell.Status.ACTIVE,
            ).count(),
            1,
        )

    @skipUnlessDBFeature("has_select_for_update")
    def test_stop_sell_lifecycle_locks_only_rows_when_source_issue_is_null(self):
        starts_at = timezone.now() - timedelta(minutes=1)
        blocker = RoomBlocker.objects.create(
            branch=self.rooms[2].branch,
            room=self.rooms[2],
            kind=RoomBlocker.Kind.MANUAL,
            status=RoomBlocker.Status.ACTIVE,
            reason="Manual blocker without nullable issue",
            starts_at=starts_at,
            created_by=self.sales,
        )
        stop_sell, _ = create_room_stop_sell(
            self.sales,
            {
                "branch": self.rooms[2].branch,
                "room": self.rooms[2],
                "blocker": blocker,
                "reason_code": RoomStopSell.ReasonCode.MAINTENANCE,
                "reason": "PostgreSQL nullable issue lock regression",
                "starts_at": starts_at,
                "planned_end_at": starts_at + timedelta(days=1),
            },
        )

        stop_sell = request_room_reopen(
            self.sales,
            stop_sell.id,
            stop_sell.version,
            "Work completed",
        )
        stop_sell = confirm_room_reopen(
            self.sales,
            stop_sell.id,
            stop_sell.version,
            "Room verified",
        )

        self.assertEqual(stop_sell.status, RoomStopSell.Status.ENDED)
        blocker.refresh_from_db()
        self.assertEqual(blocker.status, RoomBlocker.Status.CLEARED)
