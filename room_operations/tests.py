from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from housekeeping.models import Booking, HousekeepingTask, IssueTicket, TaskPhoto
from organizations.models import Branch, BranchMembership, Room

from .selectors import build_daily_schedule, build_readiness_board, build_room_profile


class RoomOperationsTests(TestCase):
    def setUp(self):
        self.founder = User.objects.create_user(username="ops-founder", role=User.Role.FOUNDER)
        self.cskh = User.objects.create_user(username="ops-cskh", role=User.Role.CUSTOMER_SERVICE)
        self.housekeeper = User.objects.create_user(
            username="ops-housekeeper",
            role=User.Role.HOUSEKEEPING,
        )
        self.outsider = User.objects.create_user(username="ops-outsider", role=User.Role.CUSTOMER_SERVICE)
        self.owner = User.objects.create_user(
            username="ops-owner", role=User.Role.BRANCH_OWNER
        )
        self.other_owner = User.objects.create_user(
            username="ops-other-owner", role=User.Role.BRANCH_OWNER
        )
        self.branch = Branch.objects.create(
            code="OPS", name="Chi nhánh vận hành", owner=self.owner
        )
        self.other_branch = Branch.objects.create(
            code="OTHER", name="Chi nhánh ngoài phạm vi", owner=self.other_owner
        )
        BranchMembership.objects.create(
            user=self.owner,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.owner,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.VIEWER,
        )
        BranchMembership.objects.create(
            user=self.cskh,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.VIEWER,
        )
        BranchMembership.objects.create(
            user=self.housekeeper,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        BranchMembership.objects.create(
            user=self.outsider,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.VIEWER,
        )
        self.ready_room = Room.objects.create(
            branch=self.branch,
            code="OPS-101",
            name="Phòng 101",
            floor="Tầng 1",
            area="Khu A",
            status=Room.Status.READY,
        )
        self.risk_room = Room.objects.create(
            branch=self.branch,
            code="OPS-102",
            name="Phòng 102",
            floor="Tầng 1",
            area="Khu A",
            status=Room.Status.WAITING_CLEANING,
        )
        self.secret_room = Room.objects.create(
            branch=self.other_branch,
            code="SECRET-201",
            name="Phòng bí mật",
            status=Room.Status.READY,
        )
        now = timezone.now()
        self.checkout_booking = Booking.objects.create(
            branch=self.branch,
            room=self.ready_room,
            code="OPS-BOOK-OUT",
            status=Booking.Status.CHECKED_IN,
            checkin_at=now - timedelta(days=2),
            checkout_at=now + timedelta(minutes=30),
            guest_name="Khách được bảo vệ",
            special_requests="Không xịt phòng",
        )
        self.checkin_booking = Booking.objects.create(
            branch=self.branch,
            room=self.risk_room,
            code="OPS-BOOK-IN",
            status=Booking.Status.BOOKED,
            checkin_at=now + timedelta(hours=2),
            checkout_at=now + timedelta(days=2),
            guest_name="Khách sắp nhận",
            special_requests="Bổ sung hai khăn tắm",
        )
        self.risk_task = HousekeepingTask.objects.create(
            code="OPS-HK-RISK",
            branch=self.branch,
            room=self.risk_room,
            booking=self.checkin_booking,
            booking_code=self.checkin_booking.code,
            task_type=HousekeepingTask.TaskType.CHECKIN_PREPARATION,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.housekeeper,
            scheduled_start_at=now - timedelta(minutes=15),
            due_at=now + timedelta(hours=1, minutes=45),
            next_checkin_at=self.checkin_booking.checkin_at,
        )
        self.issue = IssueTicket.objects.create(
            task=self.risk_task,
            room=self.risk_room,
            reported_by=self.housekeeper,
            issue_type="AIR_CONDITIONER",
            severity=HousekeepingTask.Priority.HIGH,
            description="Máy lạnh không hoạt động",
            blocks_room_ready=True,
        )
        TaskPhoto.objects.create(
            task=self.risk_task,
            room=self.risk_room,
            uploaded_by=self.housekeeper,
            category=TaskPhoto.Category.ISSUE,
            image="housekeeping/test/ops-issue.jpg",
            captured_at=now,
        )
        self.secret_booking = Booking.objects.create(
            branch=self.other_branch,
            room=self.secret_room,
            code="SECRET-BOOKING",
            checkin_at=now,
            checkout_at=now + timedelta(days=1),
            guest_name="Khách thuộc chi nhánh khác",
        )

    def authenticated(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_daily_schedule_combines_booking_tasks_requests_and_risk(self):
        schedule = build_daily_schedule(self.cskh, timezone.localdate())

        self.assertEqual(schedule["summary"]["bookingCount"], 2)
        self.assertEqual(schedule["summary"]["missingCleaningCount"], 1)
        self.assertEqual(schedule["summary"]["checkinRiskCount"], 1)
        codes = {row["booking"].code for row in schedule["rows"]}
        self.assertEqual(codes, {"OPS-BOOK-OUT", "OPS-BOOK-IN"})
        self.assertNotIn("SECRET-BOOKING", codes)

    def test_readiness_board_calculates_blockers_and_scope(self):
        board = build_readiness_board(self.cskh)
        rows = {row["room"].code: row for row in board["rows"]}

        self.assertEqual(set(rows), {"OPS-101", "OPS-102"})
        self.assertEqual(rows["OPS-101"]["state"], "READY")
        self.assertEqual(rows["OPS-102"]["state"], "BLOCKED")
        blocker_codes = {blocker["code"] for blocker in rows["OPS-102"]["blockers"]}
        self.assertIn("BLOCKING_ISSUE", blocker_codes)
        self.assertIn("CLEANLINESS_NOT_READY", blocker_codes)
        self.assertEqual(board["summary"]["blocked"], 1)

    def test_room_profile_aggregates_booking_task_issue_photo_and_timeline(self):
        profile = build_room_profile(self.cskh, self.risk_room.id)

        self.assertEqual(profile["room"], self.risk_room)
        self.assertEqual(profile["bookings"][0], self.checkin_booking)
        self.assertEqual(profile["tasks"][0], self.risk_task)
        self.assertEqual(profile["issues"][0], self.issue)
        self.assertEqual(len(profile["photos"]), 1)
        self.assertTrue({"booking", "task", "issue", "photo"}.issubset({row["kind"] for row in profile["timeline"]}))
        self.assertIsNone(build_room_profile(self.cskh, self.secret_room.id))

    def test_web_pages_render_and_protect_guest_and_branch_scope(self):
        cskh = self.authenticated(self.cskh)
        schedule = cskh.get(reverse("room_operations:schedule"))
        board = cskh.get(reverse("room_operations:room-readiness"))
        profile = cskh.get(reverse("room_operations:room-profile", args=[self.risk_room.id]))
        denied = cskh.get(reverse("room_operations:room-profile", args=[self.secret_room.id]))

        self.assertEqual(schedule.status_code, 200)
        self.assertContains(schedule, "Lịch vận hành")
        self.assertContains(schedule, "Không xịt phòng")
        self.assertContains(schedule, "Khách được bảo vệ")
        self.assertNotContains(schedule, "SECRET-BOOKING")
        self.assertContains(schedule, 'class="stat-icon"', count=6, html=False)
        self.assertContains(board, "Nguồn xác nhận chung cho CSKH, vận hành và Sales")
        self.assertContains(board, "Máy lạnh không hoạt động")
        self.assertContains(board, 'class="stat-icon"', count=7, html=False)
        self.assertContains(board, 'class="room-readiness-card state-blocked"', html=False)
        self.assertContains(profile, "Hồ sơ phòng")
        self.assertContains(profile, "Ảnh theo phòng")
        self.assertEqual(denied.status_code, 404)

        field_schedule = self.authenticated(self.housekeeper).get(reverse("room_operations:schedule"))
        self.assertContains(field_schedule, "Không xịt phòng")
        self.assertNotContains(field_schedule, "Khách được bảo vệ")

    def test_founder_can_view_all_branches(self):
        board = build_readiness_board(self.founder)
        self.assertEqual({row["room"].code for row in board["rows"]}, {"OPS-101", "OPS-102", "SECRET-201"})

    def test_owner_guest_access_is_checked_per_branch_relation(self):
        schedule = self.authenticated(self.owner).get(reverse("room_operations:schedule"))
        own_profile = self.authenticated(self.owner).get(
            reverse("room_operations:room-profile", args=[self.ready_room.id])
        )
        other_profile = self.authenticated(self.owner).get(
            reverse("room_operations:room-profile", args=[self.secret_room.id])
        )

        self.assertContains(schedule, "Khách được bảo vệ")
        self.assertContains(schedule, "SECRET-BOOKING")
        self.assertNotContains(schedule, "Khách thuộc chi nhánh khác")
        self.assertContains(own_profile, "Khách được bảo vệ")
        self.assertEqual(other_profile.status_code, 200)
        self.assertNotContains(other_profile, "Khách thuộc chi nhánh khác")
