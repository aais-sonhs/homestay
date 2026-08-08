from datetime import datetime, time, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    Branch,
    HousekeepingTask,
    IssueTicket,
    OperatingExpense,
    Room,
)
from room_operations.models import RoomAsset, RoomBlocker, RoomStopSell


class OwnerDashboardTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="dashboard-owner",
            password="Dashboard@2026",
            role=User.Role.BRANCH_OWNER,
        )
        self.other_owner = User.objects.create_user(
            username="dashboard-other-owner",
            password="Dashboard@2026",
            role=User.Role.BRANCH_OWNER,
        )
        self.housekeeper = User.objects.create_user(
            username="dashboard-housekeeper",
            password="Dashboard@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(code="DASH", name="Dashboard Đà Lạt", owner=self.owner)
        self.other_branch = Branch.objects.create(
            code="DASH-OTHER",
            name="Dashboard ngoài phạm vi",
            owner=self.other_owner,
        )
        self.today = timezone.localdate()
        self.day_start = timezone.make_aware(
            datetime.combine(self.today, time.min),
            timezone.get_current_timezone(),
        )
        self.ready_room = Room.objects.create(
            branch=self.branch,
            code="A101",
            name="Phòng A101",
            status=Room.Status.READY,
            is_guest_occupied=True,
        )
        self.arrival_room = Room.objects.create(
            branch=self.branch,
            code="A104",
            name="Phòng A104",
            status=Room.Status.WAITING_CLEANING,
        )
        self.departure_room = Room.objects.create(
            branch=self.branch,
            code="B202",
            name="Phòng B202",
            status=Room.Status.CLEANING,
        )
        self.stopped_room = Room.objects.create(
            branch=self.branch,
            code="B203",
            name="Phòng B203",
            status=Room.Status.OUT_OF_SERVICE,
        )
        self.other_room = Room.objects.create(
            branch=self.other_branch,
            code="X999",
            name="Không được phép xem",
            status=Room.Status.READY,
        )
        self.checked_in = Booking.objects.create(
            branch=self.branch,
            room=self.ready_room,
            code="BK-OCCUPIED",
            status=Booking.Status.CHECKED_IN,
            checkin_at=self.day_start - timedelta(days=1),
            checkout_at=self.day_start + timedelta(days=1),
            guest_name="Khách đang lưu trú",
            room_charge=Decimal("900000"),
        )
        self.arrival = Booking.objects.create(
            branch=self.branch,
            room=self.arrival_room,
            code="BK-ARRIVAL",
            status=Booking.Status.BOOKED,
            checkin_at=self.day_start + timedelta(hours=14),
            checkout_at=self.day_start + timedelta(days=2),
            guest_name="Khách sắp đến",
            room_charge=Decimal("1200000"),
        )
        self.departure = Booking.objects.create(
            branch=self.branch,
            room=self.departure_room,
            code="BK-DEPARTURE",
            status=Booking.Status.CHECKED_OUT,
            checkin_at=self.day_start - timedelta(days=2),
            checkout_at=self.day_start + timedelta(hours=9),
            guest_name="Khách đã trả",
            room_charge=Decimal("1500000"),
        )
        self.arrival_task = self.create_task(
            code="DASH-ARRIVAL",
            room=self.arrival_room,
            booking=self.arrival,
            status=HousekeepingTask.Status.UNASSIGNED,
            due_at=self.day_start + timedelta(hours=13),
            task_type=HousekeepingTask.TaskType.CHECKIN_PREPARATION,
        )
        self.departure_task = self.create_task(
            code="DASH-DEPARTURE",
            room=self.departure_room,
            booking=self.departure,
            status=HousekeepingTask.Status.IN_PROGRESS,
            due_at=self.day_start + timedelta(hours=12),
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
        )
        IssueTicket.objects.create(
            task=self.departure_task,
            room=self.departure_room,
            booking=self.departure,
            reported_by=self.owner,
            issue_type="AIR_CONDITIONER",
            severity=HousekeepingTask.Priority.HIGH,
            description="Điều hòa không làm lạnh",
            blocks_room_ready=True,
        )
        blocker = RoomBlocker.objects.create(
            branch=self.branch,
            room=self.stopped_room,
            kind=RoomBlocker.Kind.MAINTENANCE,
            status=RoomBlocker.Status.ACTIVE,
            reason="Bảo trì điều hòa",
            starts_at=self.day_start - timedelta(hours=1),
            created_by=self.owner,
        )
        RoomStopSell.objects.create(
            branch=self.branch,
            room=self.stopped_room,
            blocker=blocker,
            reason_code=RoomStopSell.ReasonCode.MAINTENANCE,
            reason="Bảo trì điều hòa",
            starts_at=self.day_start - timedelta(hours=1),
            planned_end_at=self.day_start + timedelta(days=1),
            created_by=self.owner,
        )
        RoomAsset.objects.create(
            branch=self.branch,
            room=self.ready_room,
            code="AC-A101",
            name="Điều hòa A101",
            category=RoomAsset.Category.AIR_CONDITIONER,
            status=RoomAsset.Status.OPERATIONAL,
        )
        RoomAsset.objects.create(
            branch=self.branch,
            room=self.departure_room,
            code="AC-B202",
            name="Điều hòa B202",
            category=RoomAsset.Category.AIR_CONDITIONER,
            status=RoomAsset.Status.FAULT,
            next_maintenance_at=self.today,
        )
        RoomAsset.objects.create(
            branch=self.other_branch,
            room=self.other_room,
            code="SECRET-ASSET",
            name="Tài sản ngoài phạm vi",
            status=RoomAsset.Status.FAULT,
        )
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Chi phí vệ sinh",
            category="Housekeeping",
            category_code=OperatingExpense.CategoryCode.HOUSEKEEPING,
            amount=Decimal("300000"),
            expense_date=self.today,
            payment_status=OperatingExpense.PaymentStatus.PAID,
            created_by=self.owner,
        )
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Sửa điều hòa",
            category="Sửa chữa kỹ thuật",
            category_code=OperatingExpense.CategoryCode.TECHNICAL_MAINTENANCE,
            amount=Decimal("500000"),
            expense_date=self.today,
            payment_status=OperatingExpense.PaymentStatus.PAID,
            created_by=self.owner,
        )

    def create_task(self, *, code, room, booking, status, due_at, task_type):
        return HousekeepingTask.objects.create(
            code=code,
            branch=self.branch,
            room=room,
            booking=booking,
            booking_code=booking.code,
            task_type=task_type,
            status=status,
            scheduled_start_at=self.day_start + timedelta(hours=8),
            due_at=due_at,
            created_by=self.owner,
        )

    def test_owner_dashboard_prioritizes_guest_risks_and_scopes_metrics(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("analytics:owner-dashboard"))
        self.assertEqual(response.status_code, 200)
        dashboard = response.context["dashboard"]
        self.assertEqual(dashboard["room"]["total"], 4)
        self.assertEqual(dashboard["room"]["occupied"], 1)
        self.assertEqual(dashboard["room"]["maintenance"], 1)
        self.assertEqual(dashboard["arrivalDeparture"]["checkinTotal"], 1)
        self.assertEqual(len(dashboard["arrivalDeparture"]["checkinRisks"]), 1)
        self.assertEqual(len(dashboard["arrivalDeparture"]["checkoutHousekeepingPending"]), 1)
        self.assertEqual(dashboard["technical"]["operational"], 1)
        self.assertEqual(dashboard["technical"]["fault"], 1)
        self.assertEqual(dashboard["technical"]["maintenanceDue"], 1)
        self.assertEqual(dashboard["financial"]["housekeepingExpense"], Decimal("300000"))
        self.assertEqual(dashboard["financial"]["technicalExpense"], Decimal("500000"))
        self.assertEqual(dashboard["financial"]["todayExpense"], Decimal("800000"))
        self.assertTrue(dashboard["financial"]["chart"]["currentPoints"])
        self.assertEqual(len(dashboard["financial"]["channelBreakdown"]), 4)
        self.assertEqual(dashboard["financial"]["channelBreakdown"][0]["code"], Booking.Source.MANUAL_SALES)
        self.assertEqual(len(dashboard["branchPerformance"]), 1)
        self.assertEqual(dashboard["branchPerformance"][0]["branch"], self.branch)
        self.assertContains(response, 'class="executive-kpi-grid"', html=False)
        self.assertContains(response, 'class="revenue-line current"', html=False)
        self.assertContains(response, 'class="executive-donut expense-donut"', html=False)
        self.assertContains(response, 'class="card executive-panel channel-panel"', html=False)
        self.assertContains(response, 'class="card executive-panel branch-performance-panel"', html=False)
        self.assertContains(response, "A104 check-in")
        self.assertContains(response, "B202")
        self.assertNotContains(response, "SECRET-ASSET")
        self.assertNotContains(response, "Dashboard ngoài phạm vi")

    def test_root_routes_management_to_overview_and_field_staff_to_tasks(self):
        self.client.force_login(self.owner)
        owner_response = self.client.get(reverse("dashboard"))
        self.assertRedirects(owner_response, reverse("analytics:owner-dashboard"))
        self.client.force_login(self.housekeeper)
        field_response = self.client.get(reverse("dashboard"))
        self.assertRedirects(field_response, reverse("housekeeping:task-list"))
        denied = self.client.get(reverse("analytics:owner-dashboard"))
        self.assertEqual(denied.status_code, 403)

    def test_owner_login_lands_on_overview(self):
        response = self.client.post(
            reverse("login"),
            {"username": self.owner.username, "password": "Dashboard@2026"},
        )
        self.assertRedirects(response, reverse("analytics:owner-dashboard"))

    def test_asset_views_do_not_expose_other_branch(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("room_operations:asset-list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AC-A101")
        self.assertNotContains(response, "SECRET-ASSET")
        foreign_asset = RoomAsset.objects.get(code="SECRET-ASSET")
        denied = self.client.get(reverse("room_operations:asset-update", args=[foreign_asset.id]))
        self.assertEqual(denied.status_code, 404)
