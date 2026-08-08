import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from accounts.models import User
from housekeeping.models import (
    Booking,
    BookingSpecialRequest,
    HousekeepingTask,
    IssueTicket,
    OutboxEvent,
    TaskPhoto,
)
from organizations.models import Room
from room_operations.models import (
    RoomAsset,
    RoomBlocker,
    RoomBlockerHistory,
    RoomStopSell,
    RoomStopSellHistory,
)
from room_operations.selectors import build_readiness_board


class OperationsDemoSeedTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            MEDIA_ROOT=self.media_directory.name,
            PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.media_directory.cleanup()

    def _demo_counts(self):
        bookings = Booking.objects.filter(code__startswith="DEMO-BK-")
        return {
            "rooms": Room.objects.filter(
                operational_note__startswith="Dữ liệu mẫu do seed_operations_demo_data"
            ).count(),
            "bookings": bookings.count(),
            "booking_tasks": HousekeepingTask.objects.filter(booking__in=bookings).count(),
            "standalone_tasks": HousekeepingTask.objects.filter(
                code__startswith="DEMO-HK-"
            ).count(),
            "requests": BookingSpecialRequest.objects.filter(booking__in=bookings).count(),
            "issues": IssueTicket.objects.filter(
                client_request_id__startswith="DEMO-ISSUE-"
            ).count(),
            "photos": TaskPhoto.objects.filter(client_id__startswith="DEMO-PHOTO-").count(),
            "blockers": RoomBlocker.objects.filter(reason__contains="[DEMO:").count(),
            "stop_sells": RoomStopSell.objects.filter(reason__startswith="[DEMO:").count(),
            "assets": RoomAsset.objects.filter(code__startswith="DEMO-").count(),
        }

    def test_seed_is_repeatable_and_covers_operational_scenarios(self):
        output = StringIO()
        call_command("seed_operations_demo_data", stdout=output)
        first_counts = self._demo_counts()
        call_command("seed_operations_demo_data", stdout=output)

        self.assertEqual(self._demo_counts(), first_counts)
        self.assertEqual(first_counts["rooms"], 11)
        self.assertEqual(first_counts["bookings"], 6)
        self.assertEqual(first_counts["booking_tasks"], 12)
        self.assertEqual(first_counts["standalone_tasks"], 2)
        self.assertEqual(first_counts["issues"], 2)
        self.assertEqual(first_counts["photos"], 4)
        self.assertEqual(first_counts["stop_sells"], 5)
        self.assertEqual(first_counts["assets"], 5)

        today_booking = Booking.objects.get(code="DEMO-BK-CHECKIN-TODAY")
        self.assertEqual(today_booking.special_request_items.count(), 7)
        self.assertEqual(
            set(today_booking.special_request_items.values_list("request_type", flat=True)),
            set(BookingSpecialRequest.RequestType.values),
        )
        preparation_task = today_booking.housekeeping_tasks.get(
            task_type=HousekeepingTask.TaskType.CHECKIN_PREPARATION
        )
        checkout_task = today_booking.housekeeping_tasks.get(
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING
        )
        self.assertEqual(len(preparation_task.special_request_items), 6)
        self.assertEqual(len(checkout_task.special_request_items), 3)

        demo_bookings = Booking.objects.filter(code__startswith="DEMO-BK-")
        demo_statuses = set(
            HousekeepingTask.objects.filter(booking__in=demo_bookings).values_list(
                "status", flat=True
            )
        ) | set(
            HousekeepingTask.objects.filter(code__startswith="DEMO-HK-").values_list(
                "status", flat=True
            )
        )
        self.assertTrue(
            {
                HousekeepingTask.Status.UNASSIGNED,
                HousekeepingTask.Status.IN_PROGRESS,
                HousekeepingTask.Status.PAUSED,
                HousekeepingTask.Status.WAITING_SUPPORT,
                HousekeepingTask.Status.COMPLETED,
                HousekeepingTask.Status.QC_APPROVED,
                HousekeepingTask.Status.CANCELLED,
            }.issubset(demo_statuses)
        )

        self.assertEqual(
            set(
                RoomStopSell.objects.filter(reason__startswith="[DEMO:").values_list(
                    "status", flat=True
                )
            ),
            set(RoomStopSell.Status.values),
        )
        self.assertEqual(
            set(
                RoomBlocker.objects.filter(reason__contains="[DEMO:").values_list(
                    "status", flat=True
                )
            ),
            set(RoomBlocker.Status.values),
        )
        reopened = RoomStopSell.objects.get(reason__startswith="[DEMO:REOPENED]")
        self.assertEqual(
            set(reopened.history.values_list("action", flat=True)),
            {
                RoomStopSellHistory.Action.CREATED,
                RoomStopSellHistory.Action.REOPEN_REQUESTED,
                RoomStopSellHistory.Action.REOPEN_CONFIRMED,
            },
        )
        self.assertTrue(
            RoomBlockerHistory.objects.filter(
                blocker=reopened.blocker,
                action=RoomBlockerHistory.Action.CLEARED,
            ).exists()
        )
        self.assertTrue(
            OutboxEvent.objects.filter(
                event_type="ROOM_STOP_SELL_ENDED",
                aggregate_id=str(reopened.id),
            ).exists()
        )

        board = build_readiness_board(User.objects.get(username="admin"))
        self.assertGreaterEqual(board["summary"]["ready"], 1)
        self.assertGreaterEqual(board["summary"]["occupied"], 1)
        self.assertGreaterEqual(board["summary"]["notReady"], 1)
        self.assertGreaterEqual(board["summary"]["blocked"], 1)
        self.assertGreaterEqual(board["summary"]["checkinRisk"], 1)
        self.assertGreaterEqual(board["summary"]["stopSell"], 1)
        self.assertIn("Dữ liệu demo vận hành đã sẵn sàng", output.getvalue())
