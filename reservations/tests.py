from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    BookingChangeLog,
    BookingSpecialRequest,
    HousekeepingActivityLog,
    HousekeepingTask,
    OutboxEvent,
    TaskSLAState,
)
from housekeeping.api.serializers import task_data
from housekeeping.services import ensure_booking_housekeeping_tasks
from organizations.models import Branch, BranchMembership, Room
from room_operations.selectors import build_daily_schedule

from .selectors import booking_creation_branch_queryset, can_create_booking_for_branch
from .services import (
    BookingCreationError,
    BookingOperationError,
    cancel_booking,
    create_booking,
    update_booking,
)


class BookingCreationTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="booking-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.other_owner = User.objects.create_user(
            username="booking-other-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.sales = User.objects.create_user(
            username="booking-sales",
            role=User.Role.SALES,
        )
        self.other_sales = User.objects.create_user(
            username="booking-other-sales",
            role=User.Role.SALES,
        )
        self.manager = User.objects.create_user(
            username="booking-manager",
            role=User.Role.MANAGER,
        )
        self.housekeeper = User.objects.create_user(
            username="booking-housekeeper",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="BOOKING-A",
            name="Chi nhánh Booking A",
            owner=self.owner,
        )
        self.other_branch = Branch.objects.create(
            code="BOOKING-B",
            name="Chi nhánh Booking B",
            owner=self.other_owner,
        )
        BranchMembership.objects.create(
            user=self.sales,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.SALES,
        )
        BranchMembership.objects.create(
            user=self.other_sales,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.SALES,
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.housekeeper,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        self.room = Room.objects.create(
            branch=self.branch,
            code="A101",
            name="Phòng A101",
            status=Room.Status.READY,
        )
        self.other_room = Room.objects.create(
            branch=self.other_branch,
            code="B201",
            name="Phòng B201",
            status=Room.Status.READY,
        )
        self.alternate_room = Room.objects.create(
            branch=self.branch,
            code="A102",
            name="Phòng A102",
            status=Room.Status.READY,
        )
        local_now = timezone.localtime().replace(second=0, microsecond=0)
        self.checkin_at = local_now + timedelta(days=3)
        self.checkout_at = self.checkin_at + timedelta(days=2)

    def payload(self, **overrides):
        data = {
            "branch": self.branch,
            "room": self.room,
            "code": "",
            "guest_name": "Nguyễn Minh Anh",
            "guest_phone": "0901234567",
            "guest_count": 2,
            "checkin_at": self.checkin_at,
            "checkout_at": self.checkout_at,
            "special_requests": "Chuẩn bị thêm một gối",
        }
        data.update(overrides)
        return data

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def structured_requests(self):
        return [
            {
                "request_type": BookingSpecialRequest.RequestType.BEDDING,
                "applies_to": BookingSpecialRequest.AppliesTo.CHECKIN,
                "priority": BookingSpecialRequest.Priority.HIGH,
                "description": "Chuẩn bị gối không lông vũ",
                "quantity": 2,
            },
            {
                "request_type": BookingSpecialRequest.RequestType.ARRIVAL,
                "applies_to": BookingSpecialRequest.AppliesTo.STAY,
                "priority": BookingSpecialRequest.Priority.NORMAL,
                "description": "Hướng dẫn lối đi không bậc thang",
            },
            {
                "request_type": BookingSpecialRequest.RequestType.HOUSEKEEPING,
                "applies_to": BookingSpecialRequest.AppliesTo.CHECKOUT,
                "priority": BookingSpecialRequest.Priority.NORMAL,
                "description": "Kiểm tra đồ khách để quên khi trả phòng",
            },
        ]

    def test_sales_creation_generates_both_cleaning_tasks_and_audit_data(self):
        booking, tasks = create_booking(self.sales, self.payload(), {"correlation_id": "booking-test"})

        self.assertEqual(booking.created_by, self.sales)
        self.assertEqual(booking.source, Booking.Source.MANUAL_SALES)
        self.assertEqual(booking.status, Booking.Status.BOOKED)
        self.assertEqual({task.task_type for task in tasks}, {
            HousekeepingTask.TaskType.CHECKIN_PREPARATION,
            HousekeepingTask.TaskType.CHECKOUT_CLEANING,
        })
        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        checkout = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )
        self.assertEqual(preparation.scheduled_start_at, self.checkin_at - timedelta(minutes=90))
        self.assertEqual(preparation.due_at, self.checkin_at - timedelta(minutes=30))
        self.assertEqual(preparation.next_checkin_at, self.checkin_at)
        self.assertFalse(preparation.requires_qc)
        self.assertEqual(checkout.scheduled_start_at, self.checkout_at)
        self.assertEqual(checkout.due_at, self.checkout_at + timedelta(minutes=60))
        self.assertTrue(checkout.requires_qc)
        self.assertEqual(preparation.checklist_items.count(), 5)
        self.assertEqual(checkout.checklist_items.count(), 5)
        self.assertEqual(TaskSLAState.objects.filter(task__in=tasks).count(), 2)
        self.assertEqual(
            sum(task.status_history.filter(reason_code="BOOKING_AUTOMATION").count() for task in tasks),
            2,
        )
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="CLEANING_TASK_GENERATED").count(),
            2,
        )
        self.assertTrue(
            OutboxEvent.objects.filter(event_type="BOOKING_CREATED", aggregate_id=str(booking.id)).exists()
        )
        self.assertTrue(
            BookingChangeLog.objects.filter(
                booking=booking,
                action=BookingChangeLog.Action.CREATED,
                booking_version=1,
            ).exists()
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, Room.Status.READY)

    def test_structured_requests_are_branch_scoped_and_snapshotted_by_task_phase(self):
        booking, tasks = create_booking(
            self.sales,
            self.payload(
                code="STRUCTURED",
                special_request_items=self.structured_requests(),
            ),
            {"correlation_id": "structured-request-test"},
        )

        stored = list(booking.special_request_items.all())
        self.assertEqual(len(stored), 3)
        self.assertEqual({item.branch_id for item in stored}, {self.branch.id})
        self.assertIn("2 × Chuẩn bị gối không lông vũ", booking.special_requests)
        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        checkout = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )
        self.assertEqual(
            {item["appliesTo"] for item in preparation.special_request_items},
            {"CHECKIN", "STAY"},
        )
        self.assertEqual(
            [item["description"] for item in checkout.special_request_items],
            ["Kiểm tra đồ khách để quên khi trả phòng"],
        )
        self.assertEqual(
            task_data(preparation, self.sales)["specialRequestItems"],
            preparation.special_request_items,
        )
        self.assertEqual(
            OutboxEvent.objects.get(
                event_type="CLEANING_TASK_GENERATED",
                aggregate_id=str(preparation.id),
            ).payload["specialRequestItems"],
            preparation.special_request_items,
        )
        creation_log = BookingChangeLog.objects.get(
            booking=booking,
            action=BookingChangeLog.Action.CREATED,
        )
        self.assertEqual(len(creation_log.after_snapshot["specialRequestItems"]), 3)
        self.assertEqual(
            OutboxEvent.objects.get(event_type="BOOKING_CREATED").payload[
                "specialRequestItems"
            ][0]["requestType"],
            "BEDDING",
        )

    def test_structured_request_update_is_atomic_with_task_lifecycle(self):
        booking, tasks = create_booking(
            self.sales,
            self.payload(
                code="STRUCTURED-UPDATE",
                special_request_items=self.structured_requests(),
            ),
        )
        changed_requests = [
            {
                "request_type": BookingSpecialRequest.RequestType.AMENITY,
                "applies_to": BookingSpecialRequest.AppliesTo.ALL,
                "priority": BookingSpecialRequest.Priority.HIGH,
                "description": "Bổ sung nước suối không ga",
                "quantity": 4,
            }
        ]
        updated, updated_tasks = update_booking(
            self.sales,
            booking.id,
            self.payload(special_request_items=changed_requests),
            booking.version,
        )

        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.special_request_items.count(), 1)
        self.assertTrue(
            all(
                task.special_request_items[0]["description"] == "Bổ sung nước suối không ga"
                for task in updated_tasks
            )
        )
        before_snapshot = BookingChangeLog.objects.get(
            booking=booking,
            action=BookingChangeLog.Action.CHANGED,
        ).before_snapshot
        self.assertEqual(len(before_snapshot["specialRequestItems"]), 3)

        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        preparation.status = HousekeepingTask.Status.IN_PROGRESS
        preparation.save(update_fields=["status"])
        with self.assertRaisesMessage(BookingOperationError, "đã bắt đầu"):
            update_booking(
                self.sales,
                booking.id,
                self.payload(
                    special_request_items=[
                        {
                            "request_type": "OTHER",
                            "applies_to": "ALL",
                            "priority": "NORMAL",
                            "description": "Không được lưu vì task đã bắt đầu",
                        }
                    ]
                ),
                updated.version,
            )
        updated.refresh_from_db()
        self.assertEqual(updated.special_request_items.get().description, "Bổ sung nước suối không ga")
        self.assertEqual(updated.version, 2)

    def test_update_booking_reschedules_same_tasks_and_sla_atomically(self):
        booking, original_tasks = create_booking(self.sales, self.payload(code="RESCHEDULE"))
        new_checkin = self.checkin_at + timedelta(hours=4)
        new_checkout = self.checkout_at + timedelta(hours=6)

        updated, tasks = update_booking(
            self.sales,
            booking.id,
            self.payload(
                room=self.alternate_room,
                checkin_at=new_checkin,
                checkout_at=new_checkout,
                special_requests="Chuẩn bị nôi em bé",
            ),
            booking.version,
            {"correlation_id": "booking-reschedule-test"},
        )

        self.assertEqual(updated.version, 2)
        self.assertEqual(updated.room, self.alternate_room)
        self.assertEqual({task.id for task in tasks}, {task.id for task in original_tasks})
        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        checkout = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )
        self.assertEqual(preparation.room, self.alternate_room)
        self.assertEqual(preparation.scheduled_start_at, new_checkin - timedelta(minutes=90))
        self.assertEqual(preparation.due_at, new_checkin - timedelta(minutes=30))
        self.assertEqual(preparation.next_checkin_at, new_checkin)
        self.assertEqual(preparation.special_request, "Chuẩn bị nôi em bé")
        self.assertEqual(checkout.scheduled_start_at, new_checkout)
        self.assertEqual(checkout.due_at, new_checkout + timedelta(minutes=60))
        self.assertEqual(preparation.sla_state.completion_due_at, preparation.due_at)
        self.assertEqual(checkout.sla_state.completion_due_at, checkout.due_at)
        self.assertEqual(
            HousekeepingActivityLog.objects.filter(
                task__in=tasks,
                action="TASK_RESCHEDULED",
                correlation_id="booking-reschedule-test",
            ).count(),
            2,
        )
        self.assertTrue(
            BookingChangeLog.objects.filter(
                booking=booking,
                action=BookingChangeLog.Action.CHANGED,
                booking_version=2,
            ).exists()
        )
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="CLEANING_TASK_RESCHEDULED").count(),
            2,
        )
        self.assertTrue(
            OutboxEvent.objects.filter(event_type="BOOKING_CHANGED", aggregate_id=str(booking.id)).exists()
        )

    def test_update_booking_rolls_back_when_an_automated_task_already_started(self):
        booking, tasks = create_booking(self.sales, self.payload(code="STARTED"))
        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        preparation.status = HousekeepingTask.Status.IN_PROGRESS
        preparation.save(update_fields=["status"])
        original_room_id = booking.room_id
        original_checkin = booking.checkin_at

        with self.assertRaisesMessage(BookingOperationError, "đã bắt đầu"):
            update_booking(
                self.sales,
                booking.id,
                self.payload(
                    room=self.alternate_room,
                    checkin_at=self.checkin_at + timedelta(hours=2),
                ),
                booking.version,
            )

        booking.refresh_from_db()
        preparation.refresh_from_db()
        self.assertEqual(booking.room_id, original_room_id)
        self.assertEqual(booking.checkin_at, original_checkin)
        self.assertEqual(booking.version, 1)
        self.assertEqual(preparation.room_id, original_room_id)
        self.assertFalse(OutboxEvent.objects.filter(event_type="BOOKING_CHANGED").exists())

    def test_update_booking_rejects_stale_version_and_cross_branch_room(self):
        booking, _ = create_booking(self.sales, self.payload(code="VERSIONED"))
        with self.assertRaisesMessage(BookingOperationError, "người khác cập nhật"):
            update_booking(
                self.sales,
                booking.id,
                self.payload(guest_count=3),
                booking.version + 1,
            )
        with self.assertRaisesMessage(BookingOperationError, "không thuộc chi nhánh"):
            update_booking(
                self.sales,
                booking.id,
                self.payload(room=self.other_room),
                booking.version,
            )

    def test_cancel_booking_cancels_tasks_and_is_idempotent(self):
        previous, previous_tasks = create_booking(
            self.sales,
            self.payload(
                code="CANCEL-PREVIOUS",
                checkin_at=self.checkin_at - timedelta(days=2),
                checkout_at=self.checkin_at - timedelta(hours=4),
            ),
        )
        previous_checkout = next(
            task for task in previous_tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )
        booking, tasks = create_booking(self.sales, self.payload(code="CANCEL-ME"))
        previous_checkout.refresh_from_db()
        self.assertEqual(previous_checkout.next_checkin_at, booking.checkin_at)

        cancelled, cancelled_tasks = cancel_booking(
            self.sales,
            booking.id,
            booking.version,
            "Khách thay đổi kế hoạch",
            {"correlation_id": "booking-cancel-test"},
        )

        self.assertEqual(cancelled.status, Booking.Status.CANCELLED)
        self.assertEqual(cancelled.version, 2)
        self.assertEqual(cancelled.cancelled_by, self.sales)
        self.assertEqual(cancelled.cancellation_reason, "Khách thay đổi kế hoạch")
        self.assertEqual({task.id for task in cancelled_tasks}, {task.id for task in tasks})
        self.assertTrue(all(task.status == HousekeepingTask.Status.CANCELLED for task in cancelled_tasks))
        self.assertEqual(
            sum(task.status_history.filter(reason_code="BOOKING_CANCELLED").count() for task in cancelled_tasks),
            2,
        )
        self.assertEqual(
            HousekeepingActivityLog.objects.filter(
                task__in=cancelled_tasks,
                action="TASK_CANCELLED",
                correlation_id="booking-cancel-test",
            ).count(),
            2,
        )
        previous_checkout.refresh_from_db()
        self.assertIsNone(previous_checkout.next_checkin_at)
        self.assertTrue(
            BookingChangeLog.objects.filter(
                booking=booking,
                action=BookingChangeLog.Action.CANCELLED,
                booking_version=2,
            ).exists()
        )

        repeated, repeated_tasks = cancel_booking(
            self.sales,
            booking.id,
            1,
            "Gửi lại cùng thao tác",
        )
        self.assertEqual(repeated.status, Booking.Status.CANCELLED)
        self.assertEqual({task.id for task in repeated_tasks}, {task.id for task in tasks})
        self.assertEqual(
            BookingChangeLog.objects.filter(
                booking=booking,
                action=BookingChangeLog.Action.CANCELLED,
            ).count(),
            1,
        )
        self.assertEqual(OutboxEvent.objects.filter(event_type="BOOKING_CANCELLED").count(), 1)

    def test_booking_task_generation_is_idempotent(self):
        booking, original_tasks = create_booking(self.sales, self.payload())
        repeated_tasks = ensure_booking_housekeeping_tasks(self.sales, booking)

        self.assertEqual(
            {task.id for task in original_tasks},
            {task.id for task in repeated_tasks},
        )
        self.assertEqual(HousekeepingTask.objects.filter(booking=booking).count(), 2)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="CLEANING_TASK_GENERATED").count(),
            2,
        )

    def test_future_checkout_task_does_not_create_false_checkin_risk(self):
        booking, tasks = create_booking(self.sales, self.payload())
        preparation = next(
            task for task in tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        preparation.status = HousekeepingTask.Status.QC_APPROVED
        preparation.save(update_fields=["status"])

        schedule = build_daily_schedule(
            self.sales,
            timezone.localdate(booking.checkin_at),
            branch_id=str(self.branch.id),
        )

        self.assertEqual(schedule["summary"]["checkinRiskCount"], 0)
        self.assertFalse(schedule["rows"][0]["checkinRisk"])

    def test_new_booking_updates_previous_checkout_task_next_checkin(self):
        previous_checkin = self.checkin_at - timedelta(days=2)
        previous_checkout = self.checkin_at - timedelta(hours=5)
        previous, previous_tasks = create_booking(
            self.sales,
            self.payload(
                code="PREVIOUS",
                checkin_at=previous_checkin,
                checkout_at=previous_checkout,
            ),
        )
        previous_checkout_task = next(
            task for task in previous_tasks
            if task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )

        create_booking(self.sales, self.payload(code="NEXT"))
        previous_checkout_task.refresh_from_db()

        self.assertEqual(previous_checkout_task.booking, previous)
        self.assertEqual(previous_checkout_task.next_checkin_at, self.checkin_at)

    def test_overlap_is_rejected_even_when_service_is_called_directly(self):
        create_booking(self.sales, self.payload(code="FIRST"))

        with self.assertRaisesMessage(BookingCreationError, "trùng khoảng thời gian"):
            create_booking(
                self.sales,
                self.payload(
                    code="OVERLAP",
                    checkin_at=self.checkin_at + timedelta(hours=1),
                    checkout_at=self.checkout_at + timedelta(hours=1),
                ),
            )
        self.assertEqual(Booking.objects.count(), 1)

    def test_sales_cannot_create_booking_for_another_branch(self):
        with self.assertRaisesMessage(BookingCreationError, "không có quyền"):
            create_booking(
                self.sales,
                self.payload(branch=self.other_branch, room=self.other_room),
            )

        page = self.client_for(self.sales).get(reverse("reservations:booking-create"))
        self.assertContains(page, self.branch.name)
        self.assertNotContains(page, self.other_branch.name)

    def test_owner_and_branch_manager_can_create_but_housekeeper_cannot(self):
        self.assertTrue(can_create_booking_for_branch(self.owner, self.branch))
        self.assertTrue(can_create_booking_for_branch(self.manager, self.branch))
        self.assertFalse(can_create_booking_for_branch(self.housekeeper, self.branch))
        self.assertEqual(list(booking_creation_branch_queryset(self.owner)), [self.branch])
        denied = self.client_for(self.housekeeper).get(reverse("reservations:booking-create"), follow=True)
        self.assertContains(denied, "chưa được cấp quyền tạo booking")

    def test_web_create_redirects_to_schedule_and_list_is_branch_scoped(self):
        checkin_value = timezone.localtime(self.checkin_at).strftime("%Y-%m-%dT%H:%M")
        checkout_value = timezone.localtime(self.checkout_at).strftime("%Y-%m-%dT%H:%M")
        response = self.client_for(self.sales).post(
            reverse("reservations:booking-create"),
            {
                "branch": str(self.branch.id),
                "room": str(self.room.id),
                "code": "WEB-BOOKING",
                "guest_name": "Khách Web",
                "guest_phone": "0912345678",
                "guest_count": 3,
                "checkin_at": checkin_value,
                "checkout_at": checkout_value,
                "special_requests": "Check-in muộn",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("room_operations:schedule"), response.url)
        self.assertIn("branchId=", response.url)
        booking = Booking.objects.get(code="WEB-BOOKING")
        Booking.objects.create(
            branch=self.other_branch,
            room=self.other_room,
            code="PRIVATE-OTHER-BRANCH",
            checkin_at=self.checkin_at,
            checkout_at=self.checkout_at,
            guest_name="Khách riêng tư",
        )
        listing = self.client_for(self.sales).get(reverse("reservations:booking-list"))

        self.assertContains(listing, booking.code)
        self.assertContains(listing, "Khách Web")
        self.assertNotContains(listing, "PRIVATE-OTHER-BRANCH")
        schedule = self.client_for(self.sales).get(
            reverse("room_operations:schedule"),
            {"date": self.checkin_at.date().isoformat(), "branchId": str(self.branch.id)},
        )
        self.assertContains(schedule, "WEB-BOOKING")
        self.assertContains(schedule, reverse("reservations:booking-create"))

    def test_web_create_accepts_multiple_structured_request_rows(self):
        checkin_value = timezone.localtime(self.checkin_at).strftime("%Y-%m-%dT%H:%M")
        checkout_value = timezone.localtime(self.checkout_at).strftime("%Y-%m-%dT%H:%M")
        response = self.client_for(self.sales).post(
            reverse("reservations:booking-create"),
            {
                "branch": str(self.branch.id),
                "room": str(self.room.id),
                "code": "WEB-STRUCTURED",
                "guest_name": "Khách có yêu cầu",
                "guest_phone": "0912345678",
                "guest_count": 2,
                "checkin_at": checkin_value,
                "checkout_at": checkout_value,
                "requests-TOTAL_FORMS": "2",
                "requests-INITIAL_FORMS": "0",
                "requests-MIN_NUM_FORMS": "0",
                "requests-MAX_NUM_FORMS": "20",
                "requests-0-request_type": "BEDDING",
                "requests-0-applies_to": "CHECKIN",
                "requests-0-priority": "HIGH",
                "requests-0-description": "Chuẩn bị chăn mỏng",
                "requests-0-quantity": "2",
                "requests-1-request_type": "HOUSEKEEPING",
                "requests-1-applies_to": "CHECKOUT",
                "requests-1-priority": "NORMAL",
                "requests-1-description": "Không dùng nước hoa phòng khi dọn",
                "requests-1-quantity": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        booking = Booking.objects.get(code="WEB-STRUCTURED")
        self.assertEqual(booking.special_request_items.count(), 2)
        schedule = self.client_for(self.sales).get(response.url)
        self.assertContains(schedule, "Giường và đồ vải")
        self.assertContains(schedule, "Trước khi nhận phòng")
        self.assertContains(schedule, "Không dùng nước hoa phòng khi dọn")

    def test_web_update_and_cancel_are_scoped_and_post_only(self):
        booking, _ = create_booking(self.sales, self.payload(code="WEB-LIFECYCLE"))
        edit_url = reverse("reservations:booking-update", args=[booking.id])
        cancel_url = reverse("reservations:booking-cancel", args=[booking.id])
        listing = self.client_for(self.sales).get(reverse("reservations:booking-list"))
        self.assertContains(listing, edit_url)
        self.assertEqual(self.client_for(self.housekeeper).get(edit_url).status_code, 403)
        self.assertEqual(self.client_for(self.other_sales).get(edit_url).status_code, 404)
        self.assertEqual(self.client_for(self.sales).get(cancel_url).status_code, 403)

        response = self.client_for(self.sales).post(
            edit_url,
            {
                "version": booking.version,
                "room": str(self.alternate_room.id),
                "guest_name": booking.guest_name,
                "guest_phone": booking.guest_phone,
                "guest_count": 4,
                "checkin_at": timezone.localtime(self.checkin_at).strftime("%Y-%m-%dT%H:%M"),
                "checkout_at": timezone.localtime(self.checkout_at).strftime("%Y-%m-%dT%H:%M"),
                "special_requests": "Bốn khách",
            },
        )
        self.assertRedirects(response, reverse("reservations:booking-list"))
        booking.refresh_from_db()
        self.assertEqual(booking.room, self.alternate_room)
        self.assertEqual(booking.guest_count, 4)

        response = self.client_for(self.sales).post(
            cancel_url,
            {"version": booking.version, "reason": "Khách yêu cầu hủy"},
        )
        self.assertRedirects(response, reverse("reservations:booking-list"))
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)

    def test_housekeeper_cannot_use_guest_search_as_a_data_oracle(self):
        booking, _ = create_booking(self.sales, self.payload(code="SEARCH-PROTECTED"))

        response = self.client_for(self.housekeeper).get(
            reverse("reservations:booking-list"),
            {"q": booking.guest_phone},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, booking.code)
        self.assertNotContains(response, booking.guest_name)
