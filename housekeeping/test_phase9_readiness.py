from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User

from .models import Branch, BranchMembership, HousekeepingTask, Room


class NearRealtimeClientContractTests(SimpleTestCase):
    """AC-26: active lists poll safely and preserve unfinished filter input."""

    def test_flutter_and_backoffice_poll_progress_every_thirty_seconds(self):
        base = Path(settings.BASE_DIR)
        home = (base / "housekeeping_app/lib/src/screens/offline_home_screen.dart").read_text()
        task_list = (base / "templates/housekeeping/task_list.html").read_text()
        dashboard = (base / "templates/housekeeping/operations_dashboard.html").read_text()
        shell = (base / "static/js/housekeeping.js").read_text()

        self.assertIn("Duration(seconds: 30)", home)
        self.assertIn("_online == true", home)
        self.assertIn("background: true", home)
        self.assertIn('data-auto-refresh-seconds="30"', task_list)
        self.assertIn('data-auto-refresh-seconds="30"', dashboard)
        self.assertIn('document.visibilityState === "visible"', shell)
        self.assertIn("hasUnsavedFormInput", shell)


class NearRealtimeProgressIntegrationTests(TestCase):
    """AC-13/AC-26, TC-07: a subsequent scoped list exposes fresh progress metadata."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="phase9-manager",
            first_name="Minh",
            role=User.Role.MANAGER,
        )
        self.worker = User.objects.create_user(
            username="phase9-worker",
            first_name="Lan",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="P9", name="Phase 9", owner=self.user
        )
        BranchMembership.objects.create(
            user=self.user,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
        )
        BranchMembership.objects.create(
            user=self.worker,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        room = Room.objects.create(branch=self.branch, code="P9-101", name="Phòng P9-101")
        now = timezone.now()
        self.task = HousekeepingTask.objects.create(
            code="P9-TASK",
            branch=self.branch,
            room=room,
            assignee=self.worker,
            status=HousekeepingTask.Status.IN_PROGRESS,
            scheduled_start_at=now,
            due_at=now + timedelta(hours=1),
            progress_percent=10,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_poll_reads_progress_user_timestamp_and_version_without_stale_response(self):
        url = reverse("housekeeping:api-task-list")
        params = {"date": timezone.localdate().isoformat()}
        first = self.client.get(url, params).json()["data"][0]
        changed_at = timezone.now()
        HousekeepingTask.objects.filter(pk=self.task.id).update(
            progress_percent=70,
            last_progress_at=changed_at,
            updated_by=self.worker,
            version=2,
        )

        second_response = self.client.get(url, params)
        second = second_response.json()["data"][0]

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(first["progressPercent"], 10)
        self.assertEqual(second["progressPercent"], 70)
        self.assertEqual(second["updatedBy"]["username"], self.worker.username)
        self.assertIsNotNone(second["lastProgressAt"])
        self.assertEqual(second["version"], 2)
