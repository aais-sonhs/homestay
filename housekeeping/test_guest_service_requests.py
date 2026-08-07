import json

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, User

from .guest_requests import (
    accept_guest_request,
    complete_guest_request,
    create_guest_request,
    start_guest_request,
)
from .models import (
    Booking,
    Branch,
    BranchMembership,
    GuestServiceRequest,
    Room,
)
from .services import HousekeepingError


class GuestServiceRequestTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="guest-manager",
            password="Test@2026",
            role=User.Role.MANAGER,
        )
        self.cskh = User.objects.create_user(
            username="guest-cskh",
            password="Test@2026",
            role=User.Role.CUSTOMER_SERVICE,
        )
        self.housekeeper = User.objects.create_user(
            username="guest-housekeeper",
            password="Test@2026",
            first_name="Cô Lan",
            role=User.Role.HOUSEKEEPING,
        )
        self.outsider = User.objects.create_user(
            username="guest-outsider",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="GUEST-DL", name="Bliss Đà Lạt", owner=self.manager
        )
        self.other_branch = Branch.objects.create(
            code="GUEST-HN", name="Bliss Hà Nội", owner=self.outsider
        )
        for user, membership_role in (
            (self.manager, BranchMembership.MembershipRole.MANAGER),
            (self.cskh, BranchMembership.MembershipRole.VIEWER),
            (self.housekeeper, BranchMembership.MembershipRole.HOUSEKEEPER),
        ):
            BranchMembership.objects.create(
                user=user,
                branch=self.branch,
                membership_role=membership_role,
            )
        BranchMembership.objects.create(
            user=self.outsider,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        self.room = Room.objects.create(
            branch=self.branch,
            code="DL-101",
            name="Phòng 101",
            is_guest_occupied=True,
        )
        self.booking = Booking.objects.create(
            branch=self.branch,
            room=self.room,
            code="BK-GUEST-001",
            status=Booking.Status.CHECKED_IN,
            guest_name="Nguyễn An",
            guest_phone="0901000000",
            checkin_at=timezone.now(),
        )
        self.payload = {
            "branchId": str(self.branch.id),
            "roomId": str(self.room.id),
            "bookingId": str(self.booking.id),
            "requestType": GuestServiceRequest.RequestType.WATER,
            "description": "Giao thêm hai chai nước suối",
            "quantity": 2,
            "unit": "chai",
            "source": GuestServiceRequest.Source.ZALO,
            "priority": GuestServiceRequest.Priority.HIGH,
        }

    def bearer_client(self, user):
        token = AccessToken.objects.create(user=user, label="Guest request test")
        client = Client()
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token.key}"
        return client

    def test_cskh_creates_request_for_checked_in_booking(self):
        item = create_guest_request(self.cskh, self.payload)

        self.assertEqual(item.status, GuestServiceRequest.Status.NEW)
        self.assertEqual(item.requested_by, self.cskh)
        self.assertEqual(item.booking, self.booking)
        self.assertEqual(item.room, self.room)
        self.assertEqual(item.quantity, 2)
        self.assertTrue(item.code.startswith("YC-"))
        self.assertEqual(item.events.count(), 1)

    def test_request_requires_matching_checked_in_booking(self):
        self.booking.status = Booking.Status.CHECKED_OUT
        self.booking.save(update_fields=["status"])

        with self.assertRaisesMessage(HousekeepingError, "đang nhận phòng"):
            create_guest_request(self.cskh, self.payload)

    def test_housekeeper_accepts_starts_and_completes(self):
        item = create_guest_request(self.cskh, self.payload)

        item = accept_guest_request(self.housekeeper, item.id, item.version)
        self.assertEqual(item.status, GuestServiceRequest.Status.ACCEPTED)
        self.assertEqual(item.assignee, self.housekeeper)

        item = start_guest_request(self.housekeeper, item.id, item.version)
        self.assertEqual(item.status, GuestServiceRequest.Status.IN_PROGRESS)

        item = complete_guest_request(
            self.housekeeper, item.id, item.version, "Đã giao tận tay khách"
        )
        self.assertEqual(item.status, GuestServiceRequest.Status.COMPLETED)
        self.assertEqual(item.resolution_note, "Đã giao tận tay khách")
        self.assertIsNotNone(item.completed_at)
        self.assertEqual(item.events.count(), 4)

    def test_outside_housekeeper_cannot_see_or_accept_request(self):
        item = create_guest_request(self.cskh, self.payload)

        response = self.bearer_client(self.outsider).get(
            reverse("housekeeping:api-guest-request-detail", args=[item.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_web_cskh_can_create_and_menu_is_visible(self):
        client = Client()
        client.force_login(self.cskh)

        page = client.get(reverse("housekeeping:guest-request-list"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Khách yêu cầu")
        self.assertContains(page, "Tạo yêu cầu")

        create_page = client.get(reverse("housekeeping:guest-request-create"))
        self.assertEqual(create_page.status_code, 200)
        self.assertContains(create_page, self.booking.code)

        response = client.post(
            reverse("housekeeping:guest-request-create"),
            self.payload,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(GuestServiceRequest.objects.count(), 1)
        detail = client.get(response.url)
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Giao thêm hai chai nước suối")

    def test_api_full_worker_flow_and_hides_guest_identity(self):
        cskh_client = self.bearer_client(self.cskh)
        created = cskh_client.post(
            reverse("housekeeping:api-guest-request-list"),
            data=json.dumps(self.payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="guest-create-1",
        )
        self.assertEqual(created.status_code, 201)
        created_data = created.json()["data"]
        item_id = created_data["id"]

        worker = self.bearer_client(self.housekeeper)
        listed = worker.get(reverse("housekeeping:api-guest-request-list"))
        self.assertEqual(listed.status_code, 200)
        row = listed.json()["data"][0]
        self.assertEqual(row["booking"]["guestName"], None)
        self.assertTrue(row["capabilities"]["accept"])

        accepted = worker.post(
            reverse("housekeeping:api-guest-request-accept", args=[item_id]),
            data=json.dumps({"version": row["version"]}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="guest-accept-1",
        )
        self.assertEqual(accepted.status_code, 200)
        accepted_data = accepted.json()["data"]

        started = worker.post(
            reverse("housekeeping:api-guest-request-start", args=[item_id]),
            data=json.dumps({"version": accepted_data["version"]}),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="guest-start-1",
        )
        self.assertEqual(started.status_code, 200)
        started_data = started.json()["data"]

        completed = worker.post(
            reverse("housekeeping:api-guest-request-complete", args=[item_id]),
            data=json.dumps(
                {"version": started_data["version"], "note": "Đã giao khách"}
            ),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="guest-complete-1",
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(
            completed.json()["data"]["status"],
            GuestServiceRequest.Status.COMPLETED,
        )

    def test_manager_can_assign_from_web(self):
        item = create_guest_request(self.cskh, self.payload)
        client = Client()
        client.force_login(self.manager)

        response = client.post(
            reverse(
                "housekeeping:guest-request-action", args=[item.id, "assign"]
            ),
            {
                "version": item.version,
                "assigneeId": str(self.housekeeper.id),
            },
        )

        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, GuestServiceRequest.Status.ASSIGNED)
        self.assertEqual(item.assignee, self.housekeeper)
