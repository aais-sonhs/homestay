from datetime import timedelta
from decimal import Decimal

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    BookingChangeLog,
    CapitalEntry,
    OperatingExpense,
    OutboxEvent,
)
from organizations.models import Branch, BranchMembership, Room

from .forms import BookingCreateForm


class RevenueReportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="revenue-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.other_owner = User.objects.create_user(
            username="revenue-other-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.manager = User.objects.create_user(
            username="revenue-manager",
            role=User.Role.MANAGER,
        )
        self.sales = User.objects.create_user(
            username="revenue-sales",
            role=User.Role.SALES,
        )
        self.branch = Branch.objects.create(
            code="REV-A",
            name="Chi nhánh doanh thu A",
            owner=self.owner,
        )
        self.other_branch = Branch.objects.create(
            code="REV-B",
            name="Chi nhánh doanh thu B",
            owner=self.other_owner,
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.sales,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.SALES,
        )
        self.room = Room.objects.create(
            branch=self.branch,
            code="R101",
            name="Phòng 101",
        )
        self.other_room = Room.objects.create(
            branch=self.other_branch,
            code="R201",
            name="Phòng 201",
        )
        local_now = timezone.localtime().replace(second=0, microsecond=0)
        self.checkin_at = local_now - timedelta(days=2)
        self.checkout_at = local_now - timedelta(days=1)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        return client

    def create_booking(self, *, branch=None, room=None, code="REV-001", **values):
        branch = branch or self.branch
        room = room or self.room
        defaults = {
            "branch": branch,
            "room": room,
            "code": code,
            "status": Booking.Status.CHECKED_OUT,
            "checkin_at": self.checkin_at,
            "checkout_at": self.checkout_at,
            "guest_name": "Khách doanh thu",
            "room_charge": Decimal("1000000.00"),
            "service_charge": Decimal("200000.00"),
            "discount_amount": Decimal("100000.00"),
            "paid_amount": Decimal("500000.00"),
        }
        defaults.update(values)
        return Booking.objects.create(**defaults)

    def test_daily_report_is_scoped_and_excludes_cancelled_bookings(self):
        self.create_booking()
        self.create_booking(
            code="REV-CANCELLED",
            status=Booking.Status.CANCELLED,
            room_charge=Decimal("9000000.00"),
            service_charge=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            paid_amount=Decimal("0.00"),
        )
        self.create_booking(
            branch=self.other_branch,
            room=self.other_room,
            code="REV-OTHER",
            room_charge=Decimal("3000000.00"),
            service_charge=Decimal("0.00"),
            discount_amount=Decimal("0.00"),
            paid_amount=Decimal("3000000.00"),
        )
        day = timezone.localdate(self.checkout_at).isoformat()

        response = self.client_for(self.owner).get(
            reverse("reservations:revenue-daily"),
            {"from_date": day, "to_date": day},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["booking_count"], 1)
        self.assertEqual(
            response.context["summary"]["total_amount"],
            Decimal("1100000.00"),
        )
        self.assertEqual(
            response.context["summary"]["paid_amount"],
            Decimal("500000.00"),
        )
        self.assertEqual(
            response.context["summary"]["outstanding_amount"],
            Decimal("600000.00"),
        )
        self.assertContains(response, "1.100.000 đ")
        self.assertNotContains(response, self.other_branch.name)

    def test_manager_can_view_monthly_report_but_sales_cannot(self):
        self.create_booking()

        manager_response = self.client_for(self.manager).get(
            reverse("reservations:revenue-monthly"),
            {"year": timezone.localdate(self.checkout_at).year},
        )
        sales_response = self.client_for(self.sales).get(
            reverse("reservations:revenue-daily")
        )

        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(manager_response.context["summary"]["booking_count"], 1)
        self.assertEqual(sales_response.status_code, 403)

    def test_booking_form_rejects_payment_above_booking_value(self):
        checkin_at = timezone.localtime() + timedelta(days=2)
        checkout_at = checkin_at + timedelta(days=1)
        form = BookingCreateForm(
            data={
                "branch": str(self.branch.id),
                "room": str(self.room.id),
                "code": "REV-FORM",
                "guest_name": "Khách form",
                "guest_phone": "0901234567",
                "guest_count": 2,
                "checkin_at": checkin_at.strftime("%Y-%m-%dT%H:%M"),
                "checkout_at": checkout_at.strftime("%Y-%m-%dT%H:%M"),
                "room_charge": "1.000.000",
                "service_charge": "100.000",
                "discount_amount": "100.000",
                "paid_amount": "1.100.000",
            },
            user=self.owner,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("paid_amount", form.errors)

    def test_owner_can_update_checked_out_financials_without_changing_stay(self):
        booking = self.create_booking()
        original_checkin_at = booking.checkin_at
        original_status = booking.status

        response = self.client_for(self.owner).post(
            reverse(
                "reservations:booking-financial-update",
                kwargs={"booking_id": booking.id},
            ),
            {
                "version": booking.version,
                "room_charge": "1.200.000",
                "service_charge": "300.000",
                "discount_amount": "100.000",
                "paid_amount": "1.400.000",
            },
        )

        self.assertRedirects(response, reverse("reservations:booking-list"))
        booking.refresh_from_db()
        self.assertEqual(booking.total_amount, Decimal("1400000.00"))
        self.assertEqual(booking.outstanding_amount, Decimal("0.00"))
        self.assertEqual(booking.checkin_at, original_checkin_at)
        self.assertEqual(booking.status, original_status)
        self.assertEqual(booking.version, 2)
        self.assertTrue(
            BookingChangeLog.objects.filter(
                booking=booking,
                action=BookingChangeLog.Action.CHANGED,
                booking_version=2,
            ).exists()
        )
        self.assertTrue(
            OutboxEvent.objects.filter(
                aggregate_id=str(booking.id),
                event_type="BOOKING_FINANCIALS_CHANGED",
            ).exists()
        )

        denied = self.client_for(self.sales).get(
            reverse(
                "reservations:booking-financial-update",
                kwargs={"booking_id": booking.id},
            )
        )
        self.assertEqual(denied.status_code, 404)

    def test_cost_dashboard_and_lists_are_branch_scoped(self):
        today = timezone.localdate()
        CapitalEntry.objects.create(
            branch=self.branch,
            title="Vốn đầu tư phòng mẫu",
            amount=Decimal("10000000.00"),
            capital_date=today,
            created_by=self.owner,
        )
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Tiền điện",
            category="Điện nước",
            amount=Decimal("1200000.00"),
            expense_date=today,
            payment_status=OperatingExpense.PaymentStatus.PAID,
            created_by=self.owner,
        )
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Sửa máy lạnh",
            category="Sửa chữa",
            amount=Decimal("800000.00"),
            expense_date=today,
            payment_status=OperatingExpense.PaymentStatus.PLANNED,
            created_by=self.owner,
        )
        response = self.client_for(self.owner).get(
            reverse("reservations:costs-dashboard"),
            {"year": today.year},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["capital_total"], Decimal("10000000.00"))
        self.assertEqual(response.context["summary"]["expense_total"], Decimal("2000000.00"))
        self.assertEqual(response.context["summary"]["paid_expense_total"], Decimal("1200000.00"))
        self.assertEqual(response.context["summary"]["net_cash"], Decimal("8800000.00"))
        self.assertContains(response, "10.000.000 đ")

        expense_list = self.client_for(self.owner).get(reverse("reservations:expense-list"))
        capital_list = self.client_for(self.owner).get(reverse("reservations:capital-list"))
        sales_response = self.client_for(self.sales).get(reverse("reservations:costs-dashboard"))
        self.assertContains(expense_list, "Tiền điện")
        self.assertContains(capital_list, "Vốn đầu tư phòng mẫu")
        self.assertEqual(sales_response.status_code, 403)

    def test_owner_can_create_operating_expense_from_web(self):
        today = timezone.localdate().isoformat()
        response = self.client_for(self.owner).post(
            reverse("reservations:expense-create"),
            {
                "branch": str(self.branch.id),
                "name": "Mua khăn",
                "category": "Vật tư",
                "amount": "350.000",
                "expense_date": today,
                "payment_status": "PAID",
                "notes": "Bổ sung kho phòng 101",
            },
        )
        self.assertRedirects(response, reverse("reservations:expense-list"))
        self.assertTrue(OperatingExpense.objects.filter(name="Mua khăn", amount=350000).exists())

    def test_profit_report_subtracts_only_paid_operating_expenses(self):
        self.create_booking()
        today = timezone.localdate()
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Chi đã thanh toán",
            amount=Decimal("300000.00"),
            expense_date=today,
            payment_status=OperatingExpense.PaymentStatus.PAID,
        )
        OperatingExpense.objects.create(
            branch=self.branch,
            name="Chi dự kiến",
            amount=Decimal("900000.00"),
            expense_date=today,
            payment_status=OperatingExpense.PaymentStatus.PLANNED,
        )
        response = self.client_for(self.owner).get(
            reverse("reservations:profit-dashboard"),
            {"year": today.year},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["summary"]["revenue_total"], Decimal("1100000.00"))
        self.assertEqual(response.context["summary"]["expense_total"], Decimal("300000.00"))
        self.assertEqual(response.context["summary"]["profit_total"], Decimal("800000.00"))
        self.assertContains(response, "800.000 đ")
