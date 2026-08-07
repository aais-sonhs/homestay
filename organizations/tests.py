from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from common.access import Capability, decide_task_capability
from housekeeping.models import (
    BranchMembership,
    BranchHousekeepingPolicy,
    HousekeepingTask,
    SLAPolicy,
    SupplyLocation,
)

from .models import Branch, BranchOwnershipHistory, Room


class BranchBackofficeTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="platform-admin",
            password="Current@2026Pass",
        )
        self.founder = User.objects.create_user(username="branch-founder", role=User.Role.FOUNDER)
        self.manager = User.objects.create_user(username="branch-manager", role=User.Role.MANAGER)
        self.owner = User.objects.create_user(
            username="dalat-owner",
            email="dalat-owner@example.com",
            role=User.Role.BRANCH_OWNER,
        )
        self.branch = Branch.objects.create(
            code="DALAT",
            name="Bliss Home Đà Lạt",
            address="Đà Lạt, Lâm Đồng",
            owner=self.owner,
        )

    def authenticated(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_founder_creates_branch_with_operational_defaults(self):
        response = self.authenticated(self.superadmin).post(
            reverse("organizations:branch-create"),
            {
                "code": "hcm-q2",
                "name": "Bliss Home Quận 2",
                "address": "TP. Hồ Chí Minh",
                "owner": self.owner.pk,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        branch = Branch.objects.get(code="HCM-Q2")
        self.assertContains(response, "Đã tạo chi nhánh Bliss Home Quận 2")
        self.assertTrue(BranchHousekeepingPolicy.objects.filter(branch=branch).exists())
        self.assertTrue(SupplyLocation.objects.filter(branch=branch, code="DEFAULT").exists())
        self.assertTrue(SLAPolicy.objects.filter(branch=branch, task_type="", priority="").exists())
        history = BranchOwnershipHistory.objects.get(branch=branch)
        self.assertEqual(history.source, BranchOwnershipHistory.Source.CREATED)
        self.assertEqual(history.new_owner, self.owner)
        self.assertEqual(history.changed_by, self.superadmin)
        membership = BranchMembership.objects.get(branch=branch, user=self.owner)
        self.assertEqual(membership.membership_role, BranchMembership.MembershipRole.MANAGER)
        self.assertTrue(membership.can_manage_team)

    def test_founder_lists_filters_and_updates_branches(self):
        inactive = Branch.objects.create(
            code="OLD", name="Chi nhánh cũ", owner=self.owner, is_active=False
        )
        client = self.authenticated(self.superadmin)

        active_page = client.get(reverse("organizations:branch-list"))
        inactive_page = client.get(reverse("organizations:branch-list"), {"status": "inactive"})
        update = client.post(
            reverse("organizations:branch-update", args=[self.branch.id]),
            {"code": "DALAT-CENTER", "name": "Bliss Home Trung tâm Đà Lạt", "address": "Phường 1", "owner": self.owner.pk},
            follow=True,
        )

        self.assertContains(active_page, self.branch.name)
        self.assertNotContains(active_page, inactive.name)
        self.assertContains(inactive_page, inactive.name)
        self.assertNotContains(inactive_page, self.branch.name)
        self.assertContains(update, "Đã cập nhật chi nhánh Bliss Home Trung tâm Đà Lạt")
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.code, "DALAT-CENTER")

    def test_branch_code_is_case_insensitively_unique(self):
        response = self.authenticated(self.superadmin).post(
            reverse("organizations:branch-create"),
            {"code": "dalat", "name": "Trùng mã", "address": "", "owner": self.owner.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mã chi nhánh đã tồn tại")
        self.assertEqual(Branch.objects.filter(code__iexact="DALAT").count(), 1)

    def test_founder_can_deactivate_and_reactivate_idle_branch(self):
        client = self.authenticated(self.superadmin)
        deactivate = client.post(
            reverse("organizations:branch-toggle-active", args=[self.branch.id]),
            {"active": "false"},
            follow=True,
        )
        self.branch.refresh_from_db()

        self.assertFalse(self.branch.is_active)
        self.assertContains(deactivate, "Đã ngừng hoạt động chi nhánh")

        reactivate = client.post(
            reverse("organizations:branch-toggle-active", args=[self.branch.id]),
            {"active": "true"},
            follow=True,
        )
        self.branch.refresh_from_db()
        self.assertTrue(self.branch.is_active)
        self.assertContains(reactivate, "Đã kích hoạt lại chi nhánh")

    def test_deactivation_is_blocked_while_task_is_open(self):
        room = Room.objects.create(branch=self.branch, code="D101", name="Phòng D101")
        HousekeepingTask.objects.create(
            code="BRANCH-OPEN-TASK",
            branch=self.branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            status=HousekeepingTask.Status.UNASSIGNED,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=1),
        )

        response = self.authenticated(self.superadmin).post(
            reverse("organizations:branch-toggle-active", args=[self.branch.id]),
            {"active": "false"},
            follow=True,
        )
        self.branch.refresh_from_db()

        self.assertTrue(self.branch.is_active)
        self.assertContains(response, "Không thể ngừng chi nhánh khi còn công việc đang mở")

    def test_only_superadmin_can_open_branch_management(self):
        for user in (self.founder, self.manager, self.owner):
            client = self.authenticated(user)
            self.assertEqual(client.get(reverse("organizations:branch-list")).status_code, 403)
            self.assertEqual(client.get(reverse("organizations:branch-create")).status_code, 403)
            self.assertEqual(client.get(reverse("organizations:branch-owner-list")).status_code, 403)

    def test_sidebar_only_shows_branch_and_owner_menus_to_superadmin(self):
        superadmin_page = self.authenticated(self.superadmin).get(reverse("housekeeping:task-list"))
        founder_page = self.authenticated(self.founder).get(reverse("housekeeping:task-list"))
        manager_page = self.authenticated(self.manager).get(reverse("housekeeping:task-list"))

        self.assertContains(superadmin_page, reverse("organizations:branch-list"))
        self.assertContains(superadmin_page, reverse("organizations:branch-owner-list"))
        self.assertContains(superadmin_page, "Quản trị hệ thống")
        self.assertContains(superadmin_page, reverse("admin:index"))
        self.assertNotContains(founder_page, reverse("organizations:branch-list"))
        self.assertNotContains(founder_page, reverse("organizations:branch-owner-list"))
        self.assertNotContains(manager_page, reverse("organizations:branch-list"))

    def test_superadmin_creates_branch_owner_account_outside_django_admin(self):
        response = self.authenticated(self.superadmin).post(
            reverse("organizations:branch-owner-create"),
            {
                "username": "hcm-owner",
                "first_name": "Minh",
                "last_name": "Nguyễn",
                "email": "hcm-owner@example.com",
                "phone_number": "0909000001",
                "is_active": "on",
                "password": "Strong@2026Pass",
                "confirm_password": "Strong@2026Pass",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        owner = User.objects.get(username="hcm-owner")
        self.assertEqual(owner.role, User.Role.BRANCH_OWNER)
        self.assertFalse(owner.is_staff)
        self.assertFalse(owner.is_superuser)
        self.assertTrue(owner.check_password("Strong@2026Pass"))
        self.assertContains(response, "Đã tạo tài khoản chủ chi nhánh")

    def test_superadmin_assigns_branch_from_owner_permission_form(self):
        new_owner = User.objects.create_user(
            username="permission-owner",
            email="permission-owner@example.com",
            role=User.Role.BRANCH_OWNER,
            is_active=True,
        )
        BranchMembership.objects.create(
            branch=self.branch,
            user=self.owner,
            membership_role=BranchMembership.MembershipRole.MANAGER,
            is_active=True,
        )
        client = self.authenticated(self.superadmin)
        form_page = client.get(
            reverse("organizations:branch-owner-update", args=[new_owner.id])
        )

        response = client.post(
            reverse("organizations:branch-owner-update", args=[new_owner.id]),
            {
                "username": new_owner.username,
                "first_name": "Mai",
                "last_name": "Nguyễn",
                "email": new_owner.email,
                "phone_number": "",
                "is_active": "on",
                "password": "",
                "confirm_password": "",
                "assign_branches": [str(self.branch.id)],
            },
            follow=True,
        )

        self.assertContains(form_page, "Gán hoặc chuyển chi nhánh")
        self.assertContains(form_page, self.branch.name)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "giao 1 chi nhánh")
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.owner, new_owner)
        self.assertFalse(
            BranchMembership.objects.get(branch=self.branch, user=self.owner).is_active
        )
        membership = BranchMembership.objects.get(branch=self.branch, user=new_owner)
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.membership_role, BranchMembership.MembershipRole.MANAGER)
        self.assertTrue(membership.can_manage_team)
        history = BranchOwnershipHistory.objects.get(branch=self.branch)
        self.assertEqual(history.previous_owner, self.owner)
        self.assertEqual(history.new_owner, new_owner)
        self.assertEqual(history.changed_by, self.superadmin)

        room = Room.objects.create(branch=self.branch, code="P-101", name="Phòng P-101")
        task = HousekeepingTask.objects.create(
            code="PERMISSION-TASK",
            branch=self.branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(decide_task_capability(new_owner, task, Capability.CANCEL).allowed)
        self.assertFalse(decide_task_capability(self.owner, task, Capability.CANCEL).allowed)

    def test_superadmin_transfers_branch_to_another_owner(self):
        new_owner = User.objects.create_user(
            username="new-owner",
            email="new-owner@example.com",
            role=User.Role.BRANCH_OWNER,
        )
        BranchMembership.objects.create(
            branch=self.branch,
            user=self.owner,
            membership_role=BranchMembership.MembershipRole.MANAGER,
            is_active=True,
        )

        response = self.authenticated(self.superadmin).post(
            reverse("organizations:branch-update", args=[self.branch.id]),
            {
                "code": self.branch.code,
                "name": self.branch.name,
                "address": self.branch.address,
                "owner": new_owner.pk,
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.branch.refresh_from_db()
        self.assertEqual(self.branch.owner, new_owner)
        self.assertFalse(
            BranchMembership.objects.get(branch=self.branch, user=self.owner).is_active
        )
        self.assertTrue(
            BranchMembership.objects.get(branch=self.branch, user=new_owner).is_active
        )
        history = BranchOwnershipHistory.objects.get(branch=self.branch)
        self.assertEqual(history.source, BranchOwnershipHistory.Source.TRANSFERRED)
        self.assertEqual(history.previous_owner, self.owner)
        self.assertEqual(history.new_owner, new_owner)
        self.assertEqual(history.changed_by, self.superadmin)
        history_page = self.authenticated(self.superadmin).get(
            reverse("organizations:branch-update", args=[self.branch.id])
        )
        self.assertContains(history_page, "Lịch sử chủ chi nhánh")
        self.assertContains(history_page, self.owner.display_name)
        self.assertContains(history_page, new_owner.display_name)

    def test_branch_owner_role_does_not_grant_management_in_another_branch(self):
        other_owner = User.objects.create_user(
            username="other-owner",
            role=User.Role.BRANCH_OWNER,
        )
        other_branch = Branch.objects.create(
            code="OTHER-SCOPE",
            name="Chi nhánh khác",
            owner=other_owner,
        )
        BranchMembership.objects.create(
            branch=other_branch,
            user=self.owner,
            membership_role=BranchMembership.MembershipRole.VIEWER,
        )
        room = Room.objects.create(branch=other_branch, code="O-101", name="Phòng O-101")
        task = HousekeepingTask.objects.create(
            code="OTHER-SCOPE-TASK",
            branch=other_branch,
            room=room,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(hours=1),
        )

        decision = decide_task_capability(self.owner, task, Capability.CANCEL)

        self.assertFalse(decision.allowed)
