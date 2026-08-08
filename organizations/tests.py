import json
from datetime import timedelta

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import AccessToken, RefreshToken, User
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


class BranchStaffApiTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="staff-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.other_owner = User.objects.create_user(
            username="other-staff-owner",
            role=User.Role.BRANCH_OWNER,
        )
        self.manager = User.objects.create_user(
            username="staff-manager",
            role=User.Role.MANAGER,
        )
        self.housekeeper = User.objects.create_user(
            username="existing-housekeeper",
            first_name="Nhân viên hiện có",
            email="existing@example.com",
            role=User.Role.HOUSEKEEPING,
        )
        self.outsider = User.objects.create_user(
            username="staff-outsider",
            role=User.Role.HOUSEKEEPING,
        )
        self.founder = User.objects.create_user(
            username="staff-founder",
            role=User.Role.FOUNDER,
        )
        self.superadmin = User.objects.create_superuser(
            username="staff-superadmin",
            password="Current@2026Pass",
        )
        self.branch = Branch.objects.create(
            code="STAFF-A",
            name="Bliss Home A",
            owner=self.owner,
        )
        self.other_branch = Branch.objects.create(
            code="STAFF-B",
            name="Bliss Home B",
            owner=self.other_owner,
        )
        BranchMembership.objects.create(
            user=self.owner,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
            can_manage_team=True,
        )
        BranchMembership.objects.create(
            user=self.manager,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.MANAGER,
            can_manage_team=True,
        )
        BranchMembership.objects.create(
            user=self.housekeeper,
            branch=self.branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        BranchMembership.objects.create(
            user=self.outsider,
            branch=self.other_branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        self.owner_token = AccessToken.objects.create(user=self.owner, label="Owner app")
        self.manager_token = AccessToken.objects.create(user=self.manager, label="Manager app")
        self.outsider_token = AccessToken.objects.create(user=self.outsider, label="Worker app")
        self.founder_token = AccessToken.objects.create(user=self.founder, label="Founder app")
        self.superadmin_token = AccessToken.objects.create(
            user=self.superadmin,
            label="Super Admin app",
        )

    def api_get(self, token, **query):
        return self.client.get(
            reverse("organizations:api-staff-collection"),
            query,
            HTTP_AUTHORIZATION=f"Bearer {token.key}",
        )

    def api_post(self, token, **overrides):
        payload = {
            "fullName": "Nguyễn Nhân Viên",
            "email": "new.staff@example.com",
            "phoneNumber": "0901234567",
            "branchId": str(self.branch.id),
            "roleKey": "housekeeping",
            "password": "Welcome@2026Safe",
            "confirmPassword": "Welcome@2026Safe",
        }
        payload.update(overrides)
        return self.client.post(
            reverse("organizations:api-staff-collection"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token.key}",
        )

    def api_assign_existing(self, token, **overrides):
        payload = {
            "identifier": "self.registered@example.com",
            "branchId": str(self.branch.id),
            "roleKey": "housekeeping",
        }
        payload.update(overrides)
        return self.client.post(
            reverse("organizations:api-staff-assign-existing"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token.key}",
        )

    def test_owner_lists_only_staff_in_owned_branches(self):
        response = self.api_get(self.owner_token)

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual([row["id"] for row in data["branches"]], [str(self.branch.id)])
        self.assertEqual(
            {row["userId"] for row in data["items"]},
            {self.manager.id, self.housekeeper.id},
        )
        self.assertNotIn(self.outsider.id, {row["userId"] for row in data["items"]})
        self.assertTrue(data["branches"][0]["canCreateManager"])
        self.assertIn("manager", {row["key"] for row in data["roleOptions"]})

    def test_owner_creates_active_qc_account_and_branch_membership(self):
        response = self.api_post(self.owner_token, roleKey="qc")

        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(email="new.staff@example.com")
        self.assertEqual(user.role, User.Role.QC)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password("Welcome@2026Safe"))
        membership = BranchMembership.objects.get(user=user, branch=self.branch)
        self.assertEqual(membership.membership_role, BranchMembership.MembershipRole.QC)
        self.assertEqual(response.json()["data"]["staff"]["branch"]["id"], str(self.branch.id))

    def test_owner_cannot_create_staff_in_another_owners_branch(self):
        response = self.api_post(
            self.owner_token,
            branchId=str(self.other_branch.id),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "BRANCH_NOT_ALLOWED")
        self.assertFalse(User.objects.filter(email="new.staff@example.com").exists())

    def test_manager_creates_lower_role_but_cannot_create_manager(self):
        created = self.api_post(self.manager_token, roleKey="housekeeping_lead")
        forbidden = self.api_post(
            self.manager_token,
            email="another.staff@example.com",
            phoneNumber="0912345678",
            roleKey="manager",
        )

        self.assertEqual(created.status_code, 201, created.content)
        membership = BranchMembership.objects.get(user__email="new.staff@example.com")
        self.assertEqual(
            membership.membership_role,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        )
        self.assertTrue(membership.can_manage_team)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(forbidden.json()["code"], "STAFF_ROLE_NOT_ALLOWED")

    def test_owner_assigns_self_registered_account_and_preserves_password(self):
        account = User.objects.create_user(
            username="self-registered",
            first_name="Người dùng tự đăng ký",
            email="self.registered@example.com",
            phone_number="0945678901",
            password="Original@2026Safe",
        )

        response = self.api_assign_existing(self.owner_token, roleKey="qc")

        self.assertEqual(response.status_code, 201, response.content)
        account.refresh_from_db()
        self.assertEqual(account.role, User.Role.QC)
        self.assertTrue(account.check_password("Original@2026Safe"))
        membership = BranchMembership.objects.get(user=account, branch=self.branch)
        self.assertEqual(membership.membership_role, BranchMembership.MembershipRole.QC)
        self.assertTrue(response.json()["data"]["existingAccountAssigned"])

    def test_manager_cannot_assign_manager_role_to_existing_account(self):
        account = User.objects.create_user(
            username="self-registered-manager",
            email="self.registered@example.com",
            phone_number="0956789012",
            password="Original@2026Safe",
        )

        response = self.api_assign_existing(self.manager_token, roleKey="manager")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "STAFF_ROLE_NOT_ALLOWED")
        account.refresh_from_db()
        self.assertEqual(account.role, User.Role.HOUSEKEEPING)
        self.assertFalse(BranchMembership.objects.filter(user=account).exists())

    def test_existing_account_cannot_be_assigned_to_a_second_branch(self):
        response = self.api_assign_existing(
            self.owner_token,
            identifier=self.housekeeper.email,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "STAFF_ACCOUNT_ALREADY_ASSIGNED")

    def test_disabled_existing_account_cannot_be_assigned(self):
        User.objects.create_user(
            username="disabled-self-registered",
            email="self.registered@example.com",
            phone_number="0967890123",
            password="Original@2026Safe",
            disabled_by_admin=True,
        )

        response = self.api_assign_existing(self.owner_token)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "STAFF_ACCOUNT_NOT_ASSIGNABLE")

    def test_field_staff_cannot_open_staff_management(self):
        response = self.api_get(self.outsider_token)
        assign_response = self.api_assign_existing(self.outsider_token)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "STAFF_MANAGEMENT_NOT_ALLOWED")
        self.assertEqual(assign_response.status_code, 403)
        self.assertEqual(
            assign_response.json()["code"],
            "STAFF_MANAGEMENT_NOT_ALLOWED",
        )

    def test_superadmin_and_founder_do_not_create_subordinate_staff(self):
        for token in (self.superadmin_token, self.founder_token):
            listed = self.api_get(token)
            created = self.api_post(token)

            self.assertEqual(listed.status_code, 403)
            self.assertEqual(created.status_code, 403)
            self.assertEqual(created.json()["code"], "STAFF_MANAGEMENT_NOT_ALLOWED")
        self.assertFalse(User.objects.filter(email="new.staff@example.com").exists())

    def test_owner_sees_web_staff_menu_and_only_owned_branch_data(self):
        self.client.force_login(self.owner)

        navigation_page = self.client.get(reverse("housekeeping:task-list"))
        staff_page = self.client.get(reverse("organizations:branch-staff-list"))

        self.assertContains(navigation_page, "Nhân sự chi nhánh")
        self.assertContains(
            navigation_page,
            reverse("organizations:branch-staff-list"),
        )
        self.assertContains(staff_page, self.branch.name)
        self.assertContains(staff_page, self.housekeeper.display_name)
        self.assertNotContains(staff_page, self.other_branch.name)
        self.assertNotContains(staff_page, self.outsider.display_name)

    def test_owner_creates_staff_from_web(self):
        self.client.force_login(self.owner)
        create_page = self.client.get(
            reverse("organizations:branch-staff-create")
        )
        response = self.client.post(
            reverse("organizations:branch-staff-create"),
            {
                "branch": str(self.branch.id),
                "role_key": "qc",
                "full_name": "Nhân viên QC Web",
                "username": "qc.web",
                "email": "web.qc@example.com",
                "phone_number": "0923456789",
                "password": "Welcome@2026Safe",
                "confirm_password": "Welcome@2026Safe",
            },
            follow=True,
        )

        self.assertEqual(create_page.status_code, 200)
        self.assertContains(create_page, "Tên đăng nhập")
        self.assertContains(create_page, 'name="username"', html=False)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đã tạo tài khoản Nhân viên QC Web")
        user = User.objects.get(email="web.qc@example.com")
        self.assertEqual(user.username, "qc.web")
        self.assertEqual(user.role, User.Role.QC)
        membership = BranchMembership.objects.get(user=user)
        self.assertEqual(membership.branch, self.branch)
        self.assertEqual(membership.membership_role, BranchMembership.MembershipRole.QC)

    def test_owner_cannot_create_staff_with_duplicate_username(self):
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse("organizations:branch-staff-create"),
            {
                "branch": str(self.branch.id),
                "role_key": "housekeeping",
                "full_name": "Nhân viên trùng tài khoản",
                "username": self.owner.username.upper(),
                "email": "duplicate.username@example.com",
                "phone_number": "0923456790",
                "password": "Welcome@2026Safe",
                "confirm_password": "Welcome@2026Safe",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("username", response.context["form"].errors)
        self.assertFalse(
            User.objects.filter(email="duplicate.username@example.com").exists()
        )

    def test_owner_edits_staff_from_web_without_resetting_password(self):
        self.housekeeper.phone_number = "0901000001"
        self.housekeeper.set_password("Original@2026Safe")
        self.housekeeper.save()
        membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        original_password_hash = self.housekeeper.password
        self.client.force_login(self.owner)

        edit_page = self.client.get(
            reverse(
                "organizations:branch-staff-update",
                args=[membership.id],
            )
        )
        staff_page = self.client.get(
            reverse("organizations:branch-staff-list")
        )
        response = self.client.post(
            reverse(
                "organizations:branch-staff-update",
                args=[membership.id],
            ),
            {
                "branch": str(self.branch.id),
                "role_key": "qc",
                "full_name": "Nhân viên đã cập nhật",
                "username": "updated.housekeeper",
                "email": "updated.staff@example.com",
                "phone_number": "0901000002",
                "password": "",
                "confirm_password": "",
                "is_active": "on",
            },
            follow=True,
        )

        self.assertEqual(edit_page.status_code, 200)
        self.assertContains(edit_page, "Chỉnh sửa Nhân viên hiện có")
        self.assertContains(
            staff_page,
            reverse("organizations:branch-staff-update", args=[membership.id]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đã cập nhật nhân sự Nhân viên đã cập nhật")
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        self.assertEqual(self.housekeeper.first_name, "Nhân viên đã cập nhật")
        self.assertEqual(self.housekeeper.username, "updated.housekeeper")
        self.assertEqual(self.housekeeper.email, "updated.staff@example.com")
        self.assertEqual(self.housekeeper.normalized_phone, "+84901000002")
        self.assertEqual(self.housekeeper.role, User.Role.QC)
        self.assertEqual(self.housekeeper.password, original_password_hash)
        self.assertTrue(self.housekeeper.check_password("Original@2026Safe"))
        self.assertTrue(self.housekeeper.is_active)
        self.assertEqual(
            membership.membership_role,
            BranchMembership.MembershipRole.QC,
        )
        self.assertTrue(membership.is_active)

    def test_owner_can_disable_staff_and_set_a_new_password(self):
        self.housekeeper.phone_number = "0902000001"
        self.housekeeper.set_password("Original@2026Safe")
        self.housekeeper.save()
        access_token = AccessToken.objects.create(
            user=self.housekeeper,
            label="Old staff phone",
        )
        refresh_token = RefreshToken.objects.create(
            user=self.housekeeper,
            expires_at=timezone.now() + timedelta(days=30),
        )
        membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "organizations:branch-staff-update",
                args=[membership.id],
            ),
            {
                "branch": str(self.branch.id),
                "role_key": "housekeeping",
                "full_name": self.housekeeper.display_name,
                "username": self.housekeeper.username,
                "email": self.housekeeper.email,
                "phone_number": self.housekeeper.phone_number,
                "password": "Changed@2026Safe",
                "confirm_password": "Changed@2026Safe",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        access_token.refresh_from_db()
        refresh_token.refresh_from_db()
        self.assertFalse(self.housekeeper.is_active)
        self.assertFalse(membership.is_active)
        self.assertTrue(self.housekeeper.check_password("Changed@2026Safe"))
        self.assertIsNotNone(access_token.revoked_at)
        self.assertIsNotNone(refresh_token.revoked_at)

    def test_owner_locks_and_unlocks_staff_from_list_action(self):
        membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        access_token = AccessToken.objects.create(
            user=self.housekeeper,
            label="Staff lock action",
        )
        refresh_token = RefreshToken.objects.create(
            user=self.housekeeper,
            expires_at=timezone.now() + timedelta(days=30),
        )
        action_url = reverse(
            "organizations:branch-staff-toggle-active",
            args=[membership.id],
        )
        self.client.force_login(self.owner)

        list_page = self.client.get(reverse("organizations:branch-staff-list"))
        get_response = self.client.get(action_url)
        lock_response = self.client.post(action_url, follow=True)

        self.assertContains(list_page, action_url)
        self.assertContains(list_page, "Khóa tài khoản")
        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(lock_response.status_code, 200)
        self.assertContains(lock_response, "Đã khóa tài khoản Nhân viên hiện có")
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        access_token.refresh_from_db()
        refresh_token.refresh_from_db()
        self.assertFalse(self.housekeeper.is_active)
        self.assertFalse(membership.is_active)
        self.assertIsNotNone(access_token.revoked_at)
        self.assertIsNotNone(refresh_token.revoked_at)

        unlock_response = self.client.post(action_url, follow=True)

        self.assertEqual(unlock_response.status_code, 200)
        self.assertContains(
            unlock_response,
            "Đã mở khóa tài khoản Nhân viên hiện có",
        )
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        self.assertTrue(self.housekeeper.is_active)
        self.assertTrue(membership.is_active)

    def test_owner_cannot_edit_staff_from_another_branch(self):
        outsider_membership = self.outsider.branch_memberships.get(
            branch=self.other_branch
        )
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse(
                "organizations:branch-staff-update",
                args=[outsider_membership.id],
            )
        )
        delete_response = self.client.post(
            reverse(
                "organizations:branch-staff-delete",
                args=[outsider_membership.id],
            )
        )
        toggle_response = self.client.post(
            reverse(
                "organizations:branch-staff-toggle-active",
                args=[outsider_membership.id],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)
        self.assertEqual(toggle_response.status_code, 404)
        self.outsider.refresh_from_db()
        self.assertFalse(self.outsider.is_deleted)

    def test_owner_soft_deletes_staff_and_revokes_tokens(self):
        membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        access_token = AccessToken.objects.create(
            user=self.housekeeper,
            label="Staff phone",
        )
        refresh_token = RefreshToken.objects.create(
            user=self.housekeeper,
            expires_at=timezone.now() + timedelta(days=30),
        )
        self.client.force_login(self.owner)

        delete_page = self.client.get(
            reverse(
                "organizations:branch-staff-delete",
                args=[membership.id],
            )
        )
        response = self.client.post(
            reverse(
                "organizations:branch-staff-delete",
                args=[membership.id],
            ),
            follow=True,
        )

        self.assertEqual(delete_page.status_code, 403)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Đã xóa nhân sự Nhân viên hiện có")
        self.assertNotIn(membership, list(response.context["memberships"]))
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        access_token.refresh_from_db()
        refresh_token.refresh_from_db()
        self.assertTrue(self.housekeeper.is_deleted)
        self.assertFalse(self.housekeeper.is_active)
        self.assertFalse(membership.is_active)
        self.assertIsNotNone(access_token.revoked_at)
        self.assertIsNotNone(refresh_token.revoked_at)

    def test_deleting_one_of_multiple_memberships_keeps_account_active(self):
        second_branch = Branch.objects.create(
            code="STAFF-C",
            name="Bliss Home C",
            owner=self.owner,
        )
        second_membership = BranchMembership.objects.create(
            user=self.housekeeper,
            branch=second_branch,
            membership_role=BranchMembership.MembershipRole.HOUSEKEEPER,
        )
        membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "organizations:branch-staff-delete",
                args=[membership.id],
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"Đã gỡ nhân sự {self.housekeeper.display_name} khỏi {self.branch.name}",
        )
        self.housekeeper.refresh_from_db()
        membership.refresh_from_db()
        second_membership.refresh_from_db()
        self.assertFalse(self.housekeeper.is_deleted)
        self.assertTrue(self.housekeeper.is_active)
        self.assertFalse(membership.is_active)
        self.assertTrue(second_membership.is_active)

    def test_manager_cannot_edit_self_or_promote_staff_to_manager(self):
        manager_membership = self.manager.branch_memberships.get(branch=self.branch)
        staff_membership = self.housekeeper.branch_memberships.get(branch=self.branch)
        self.client.force_login(self.manager)

        self_edit = self.client.get(
            reverse(
                "organizations:branch-staff-update",
                args=[manager_membership.id],
            )
        )
        self_delete = self.client.post(
            reverse(
                "organizations:branch-staff-delete",
                args=[manager_membership.id],
            )
        )
        self_toggle = self.client.post(
            reverse(
                "organizations:branch-staff-toggle-active",
                args=[manager_membership.id],
            )
        )
        promotion = self.client.post(
            reverse(
                "organizations:branch-staff-update",
                args=[staff_membership.id],
            ),
            {
                "branch": str(self.branch.id),
                "role_key": "manager",
                "full_name": self.housekeeper.display_name,
                "username": self.housekeeper.username,
                "email": self.housekeeper.email,
                "phone_number": "0903000001",
                "password": "",
                "confirm_password": "",
                "is_active": "on",
            },
        )

        self.assertEqual(self_edit.status_code, 403)
        self.assertEqual(self_delete.status_code, 403)
        self.assertEqual(self_toggle.status_code, 403)
        self.assertEqual(promotion.status_code, 200)
        self.assertIn("role_key", promotion.context["form"].errors)
        self.housekeeper.refresh_from_db()
        self.assertEqual(self.housekeeper.role, User.Role.HOUSEKEEPING)

    def test_manager_cannot_create_manager_from_web(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("organizations:branch-staff-create"),
            {
                "branch": str(self.branch.id),
                "role_key": "manager",
                "full_name": "Quản lý không hợp lệ",
                "username": "invalid.manager",
                "email": "invalid.manager@example.com",
                "phone_number": "0934567890",
                "password": "Welcome@2026Safe",
                "confirm_password": "Welcome@2026Safe",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("role_key", response.context["form"].errors)
        self.assertFalse(User.objects.filter(email="invalid.manager@example.com").exists())

    def test_superadmin_cannot_open_branch_staff_web_pages(self):
        self.client.force_login(self.superadmin)

        self.assertEqual(
            self.client.get(reverse("organizations:branch-staff-list")).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("organizations:branch-staff-create")).status_code,
            403,
        )
