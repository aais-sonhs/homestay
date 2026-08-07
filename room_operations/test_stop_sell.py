from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    HousekeepingTask,
    IssueTicket,
    OutboxEvent,
)
from housekeeping.services import report_issue, update_issue_status
from organizations.models import Branch, BranchMembership, Room
from reservations.services import (
    BookingCreationError,
    BookingOperationError,
    create_booking,
    update_booking,
)

from .models import (
    RoomBlocker,
    RoomBlockerHistory,
    RoomStopSell,
    RoomStopSellHistory,
)
from .selectors import build_daily_schedule, build_readiness_board, build_room_profile
from .services import (
    RoomOperationsError,
    cancel_scheduled_stop_sell,
    confirm_room_blocker_clearance,
    confirm_room_reopen,
    create_room_stop_sell,
    request_room_reopen,
)


class RoomStopSellTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="stop-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.other_owner = User.objects.create_user(
            username="stop-other-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.manager = User.objects.create_user(
            username="stop-manager",
            role=User.Role.MANAGER,
        )
        self.sales = User.objects.create_user(
            username="stop-sales",
            role=User.Role.SALES,
        )
        self.housekeeper = User.objects.create_user(
            username="stop-housekeeper",
            role=User.Role.HOUSEKEEPING,
        )
        self.other_manager = User.objects.create_user(
            username="stop-other-manager",
            role=User.Role.MANAGER,
        )
        self.branch = Branch.objects.create(
            code="STOP-A",
            name="Chi nhánh Stop Sell A",
            owner=self.owner,
        )
        self.other_branch = Branch.objects.create(
            code="STOP-B",
            name="Chi nhánh Stop Sell B",
            owner=self.other_owner,
        )
        for user, branch, role in (
            (self.manager, self.branch, BranchMembership.MembershipRole.MANAGER),
            (self.sales, self.branch, BranchMembership.MembershipRole.SALES),
            (self.housekeeper, self.branch, BranchMembership.MembershipRole.HOUSEKEEPER),
            (self.other_manager, self.other_branch, BranchMembership.MembershipRole.MANAGER),
        ):
            BranchMembership.objects.create(
                user=user,
                branch=branch,
                membership_role=role,
            )
        self.room = Room.objects.create(
            branch=self.branch,
            code="S101",
            name="Phòng S101",
            status=Room.Status.READY,
        )
        self.alternate_room = Room.objects.create(
            branch=self.branch,
            code="S102",
            name="Phòng S102",
            status=Room.Status.READY,
        )
        self.other_room = Room.objects.create(
            branch=self.other_branch,
            code="X201",
            name="Phòng X201",
            status=Room.Status.READY,
        )
        self.now = timezone.now().replace(second=0, microsecond=0)

    def stop_sell_payload(self, **overrides):
        payload = {
            "branch": self.branch,
            "room": self.room,
            "blocker": None,
            "reason_code": RoomStopSell.ReasonCode.MAINTENANCE,
            "reason": "Máy lạnh cần sửa trước khi bán lại",
            "starts_at": self.now + timedelta(days=2),
            "planned_end_at": self.now + timedelta(days=3),
        }
        payload.update(overrides)
        return payload

    def booking_payload(self, **overrides):
        payload = {
            "branch": self.branch,
            "room": self.room,
            "code": "",
            "guest_name": "Khách Stop Sell",
            "guest_phone": "0901234567",
            "guest_count": 2,
            "checkin_at": self.now + timedelta(days=2, hours=2),
            "checkout_at": self.now + timedelta(days=2, hours=20),
            "special_request_items": [],
        }
        payload.update(overrides)
        return payload

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_create_is_branch_scoped_audited_and_blocks_booking_service(self):
        existing, _ = create_booking(
            self.sales,
            self.booking_payload(
                room=self.alternate_room,
                code="EXISTING-AFFECTED",
            ),
        )
        stop_sell, affected_count = create_room_stop_sell(
            self.manager,
            self.stop_sell_payload(room=self.alternate_room),
            {"correlation_id": "stop-sell-create"},
        )

        self.assertEqual(affected_count, 1)
        self.assertEqual(stop_sell.branch, self.branch)
        self.assertEqual(stop_sell.blocker.branch, self.branch)
        self.assertEqual(stop_sell.blocker.room, self.alternate_room)
        self.assertEqual(stop_sell.blocker.status, RoomBlocker.Status.ACTIVE)
        self.assertTrue(
            RoomBlockerHistory.objects.filter(
                blocker=stop_sell.blocker,
                action=RoomBlockerHistory.Action.CREATED,
            ).exists()
        )
        self.assertTrue(
            RoomStopSellHistory.objects.filter(
                stop_sell=stop_sell,
                action=RoomStopSellHistory.Action.CREATED,
            ).exists()
        )
        event = OutboxEvent.objects.get(
            event_type="ROOM_STOP_SELL_STARTED",
            aggregate_id=str(stop_sell.id),
        )
        self.assertEqual(event.payload["affectedBookingCount"], 1)
        with self.assertRaisesMessage(BookingCreationError, "đang dừng bán"):
            create_booking(
                self.sales,
                self.booking_payload(
                    room=self.alternate_room,
                    code="BLOCKED-BY-STOP-SELL",
                    checkin_at=existing.checkin_at + timedelta(minutes=5),
                    checkout_at=existing.checkout_at + timedelta(hours=2),
                ),
            )
        with self.assertRaisesMessage(BookingCreationError, "đang dừng bán"):
            create_booking(
                self.sales,
                self.booking_payload(
                    room=self.alternate_room,
                    code="BLOCKED-AFTER-PLANNED-END",
                    checkin_at=stop_sell.planned_end_at + timedelta(hours=2),
                    checkout_at=stop_sell.planned_end_at + timedelta(days=1),
                ),
            )

    def test_reopen_requires_two_transitions_and_keeps_audit_snapshots(self):
        stop_sell, _ = create_room_stop_sell(
            self.manager,
            self.stop_sell_payload(
                starts_at=self.now,
                planned_end_at=self.now + timedelta(days=1),
            ),
        )
        requested = request_room_reopen(
            self.manager,
            stop_sell.id,
            stop_sell.version,
            "Kỹ thuật đã sửa xong, chờ kiểm tra",
        )
        self.assertEqual(requested.status, RoomStopSell.Status.REOPEN_REQUESTED)
        requested.blocker.refresh_from_db()
        self.assertEqual(requested.blocker.status, RoomBlocker.Status.CLEARANCE_PENDING)
        with self.assertRaisesMessage(RoomOperationsError, "người khác cập nhật"):
            confirm_room_reopen(
                self.owner,
                requested.id,
                1,
                "Phiên bản cũ",
            )

        reopened = confirm_room_reopen(
            self.owner,
            requested.id,
            requested.version,
            "Đã kiểm tra thực tế, phòng hoạt động bình thường",
        )

        self.assertEqual(reopened.status, RoomStopSell.Status.ENDED)
        self.assertEqual(reopened.reopened_by, self.owner)
        reopened.blocker.refresh_from_db()
        self.assertEqual(reopened.blocker.status, RoomBlocker.Status.CLEARED)
        self.assertEqual(
            list(reopened.history.order_by("stop_sell_version").values_list("action", flat=True)),
            [
                RoomStopSellHistory.Action.CREATED,
                RoomStopSellHistory.Action.REOPEN_REQUESTED,
                RoomStopSellHistory.Action.REOPEN_CONFIRMED,
            ],
        )
        self.assertTrue(
            OutboxEvent.objects.filter(
                event_type="ROOM_STOP_SELL_ENDED",
                aggregate_id=str(reopened.id),
            ).exists()
        )
        booking, _ = create_booking(self.sales, self.booking_payload(code="AFTER-REOPEN"))
        self.assertEqual(booking.room, self.room)

    def test_existing_affected_booking_allows_guest_edit_but_not_reschedule(self):
        booking, _ = create_booking(
            self.sales,
            self.booking_payload(code="EXISTING-DURING-STOP"),
        )
        create_room_stop_sell(self.manager, self.stop_sell_payload())
        updated, _ = update_booking(
            self.sales,
            booking.id,
            {
                **self.booking_payload(code=booking.code),
                "guest_name": "Khách đổi tên liên hệ",
            },
            booking.version,
        )
        self.assertEqual(updated.guest_name, "Khách đổi tên liên hệ")
        with self.assertRaisesMessage(BookingOperationError, "đang dừng bán"):
            update_booking(
                self.sales,
                booking.id,
                {
                    **self.booking_payload(code=booking.code),
                    "guest_name": updated.guest_name,
                    "checkin_at": booking.checkin_at + timedelta(hours=1),
                    "checkout_at": booking.checkout_at + timedelta(hours=1),
                },
                updated.version,
            )

    def test_scheduled_stop_sell_overlap_and_cancel_are_safe(self):
        stop_sell, _ = create_room_stop_sell(self.manager, self.stop_sell_payload())
        with self.assertRaisesMessage(RoomOperationsError, "đã có lịch dừng bán"):
            create_room_stop_sell(
                self.owner,
                self.stop_sell_payload(
                    starts_at=self.now + timedelta(days=2, hours=1),
                    planned_end_at=self.now + timedelta(days=4),
                ),
            )
        cancelled = cancel_scheduled_stop_sell(
            self.manager,
            stop_sell.id,
            stop_sell.version,
            "Kế hoạch sửa chữa được dời sang tháng sau",
        )
        self.assertEqual(cancelled.status, RoomStopSell.Status.CANCELLED)
        cancelled.blocker.refresh_from_db()
        self.assertEqual(cancelled.blocker.status, RoomBlocker.Status.CANCELLED)
        replacement, _ = create_room_stop_sell(self.manager, self.stop_sell_payload())
        self.assertEqual(replacement.status, RoomStopSell.Status.ACTIVE)

    def test_blocking_issue_becomes_clearance_pending_not_automatically_cleared(self):
        task = HousekeepingTask.objects.create(
            code="STOP-ISSUE-TASK",
            branch=self.branch,
            room=self.room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.housekeeper,
            scheduled_start_at=self.now,
            due_at=self.now + timedelta(hours=1),
        )
        issue, _ = report_issue(
            self.housekeeper,
            task.id,
            {
                "version": task.version,
                "issueType": "AIR_CONDITIONER",
                "severity": HousekeepingTask.Priority.HIGH,
                "description": "Máy lạnh chảy nước",
                "blocksRoomReady": True,
            },
            {"correlation_id": "issue-blocker-create"},
        )
        blocker = RoomBlocker.objects.get(issue=issue)
        self.assertEqual(blocker.branch, self.branch)
        self.assertEqual(blocker.status, RoomBlocker.Status.ACTIVE)

        issue, _ = update_issue_status(
            self.manager,
            issue.id,
            issue.version,
            IssueTicket.Status.RESOLVED,
            "Đã thay ống thoát nước",
            {},
        )
        blocker.refresh_from_db()
        self.assertEqual(blocker.status, RoomBlocker.Status.CLEARANCE_PENDING)
        board = build_readiness_board(self.sales)
        row = next(item for item in board["rows"] if item["room"] == self.room)
        self.assertEqual(row["state"], "BLOCKED")
        self.assertEqual(row["salesStatus"], "BLOCKED")

        blocker = confirm_room_blocker_clearance(
            self.manager,
            blocker.id,
            blocker.version,
            "Vận hành đã kiểm tra, không còn rò nước",
        )
        self.assertEqual(blocker.status, RoomBlocker.Status.CLEARED)

    def test_issue_linked_stop_sell_cannot_reopen_before_source_is_resolved(self):
        task = HousekeepingTask.objects.create(
            code="STOP-LINKED-ISSUE-TASK",
            branch=self.branch,
            room=self.room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.housekeeper,
            scheduled_start_at=self.now,
            due_at=self.now + timedelta(hours=1),
        )
        issue, _ = report_issue(
            self.housekeeper,
            task.id,
            {
                "version": task.version,
                "issueType": "ELECTRICITY",
                "severity": HousekeepingTask.Priority.URGENT,
                "description": "Ổ điện phát tia lửa",
                "blocksRoomReady": True,
            },
            {},
        )
        blocker = RoomBlocker.objects.get(issue=issue)
        stop_sell, _ = create_room_stop_sell(
            self.manager,
            self.stop_sell_payload(
                blocker=blocker,
                starts_at=self.now,
                planned_end_at=self.now + timedelta(days=1),
                reason_code=RoomStopSell.ReasonCode.SAFETY,
                reason="Dừng bán vì nguy cơ chập điện",
            ),
        )
        with self.assertRaisesMessage(RoomOperationsError, "chưa được xử lý xong"):
            request_room_reopen(
                self.manager,
                stop_sell.id,
                stop_sell.version,
                "Thử mở khi sự cố còn hoạt động",
            )

        issue, _ = update_issue_status(
            self.manager,
            issue.id,
            issue.version,
            IssueTicket.Status.RESOLVED,
            "Đã thay ổ điện và đo an toàn",
            {},
        )
        blocker.refresh_from_db()
        with self.assertRaisesMessage(RoomOperationsError, "mở bán lại trước"):
            confirm_room_blocker_clearance(
                self.manager,
                blocker.id,
                blocker.version,
                "Không được bỏ qua stop sell",
            )
        stop_sell = request_room_reopen(
            self.manager,
            stop_sell.id,
            stop_sell.version,
            "Nguồn sự cố đã xử lý, xin kiểm tra",
        )
        stop_sell = confirm_room_reopen(
            self.owner,
            stop_sell.id,
            stop_sell.version,
            "Đã kiểm tra tại phòng",
        )
        blocker.refresh_from_db()
        self.assertEqual(stop_sell.status, RoomStopSell.Status.ENDED)
        self.assertEqual(blocker.status, RoomBlocker.Status.CLEARED)

    def test_sales_is_read_only_and_cross_branch_records_are_hidden(self):
        stop_sell, _ = create_room_stop_sell(self.manager, self.stop_sell_payload())
        listing = self.client_for(self.sales).get(reverse("room_operations:stop-sell-list"))
        self.assertContains(listing, stop_sell.reason)
        self.assertContains(listing, "Chế độ chỉ đọc")
        denied = self.client_for(self.sales).post(
            reverse("room_operations:stop-sell-cancel", args=[stop_sell.id]),
            {"version": stop_sell.version, "note": "Không được phép"},
        )
        self.assertEqual(denied.status_code, 403)
        outsider = self.client_for(self.other_manager).get(reverse("room_operations:stop-sell-list"))
        self.assertNotContains(outsider, stop_sell.reason)
        hidden = self.client_for(self.other_manager).post(
            reverse("room_operations:stop-sell-cancel", args=[stop_sell.id]),
            {"version": stop_sell.version, "note": "Không thấy bản ghi"},
        )
        self.assertEqual(hidden.status_code, 404)

    def test_web_create_and_read_models_show_stop_sell_consistently(self):
        response = self.client_for(self.manager).post(
            reverse("room_operations:stop-sell-create"),
            {
                "branch": str(self.branch.id),
                "room": str(self.room.id),
                "blocker": "",
                "reason_code": RoomStopSell.ReasonCode.OWNER_HOLD,
                "reason": "Chủ nhà tạm giữ phòng để kiểm tra nội thất",
                "starts_at": timezone.localtime(self.now).strftime("%Y-%m-%dT%H:%M"),
                "planned_end_at": timezone.localtime(self.now + timedelta(days=1)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
            },
        )
        self.assertRedirects(response, reverse("room_operations:stop-sell-list"))
        stop_sell = RoomStopSell.objects.get(room=self.room)
        board = build_readiness_board(self.sales)
        row = next(item for item in board["rows"] if item["room"] == self.room)
        self.assertEqual(row["salesStatus"], "STOP_SELL")
        profile = build_room_profile(self.sales, self.room.id)
        self.assertEqual(profile["stopSells"][0], stop_sell)
        self.assertEqual(profile["blockers"][0], stop_sell.blocker)
        self.assertTrue(
            {"blocker", "stop-sell"}.issubset({item["kind"] for item in profile["timeline"]})
        )
        schedule = build_daily_schedule(
            self.sales,
            timezone.localdate(self.now),
            branch_id=str(self.branch.id),
        )
        self.assertEqual(schedule["summary"]["bookingCount"], 0)
        page = self.client_for(self.sales).get(reverse("room_operations:room-readiness"))
        self.assertContains(page, "Dừng bán")
        self.assertContains(page, stop_sell.reason)
