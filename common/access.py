from dataclasses import dataclass

from django.db.models import Count, F, Q
from django.utils import timezone

from accounts.models import User

from housekeeping.models import HousekeepingTask, ShiftAssignment
from organizations.models import BranchMembership


GLOBAL_ROLES = {User.Role.FOUNDER}
MANAGEMENT_ROLES = GLOBAL_ROLES | {User.Role.BRANCH_OWNER, User.Role.MANAGER}
FIELD_ROLES = MANAGEMENT_ROLES | {User.Role.HOUSEKEEPING}
QC_ROLES = MANAGEMENT_ROLES | {User.Role.QC}


class Capability:
    VIEW = "VIEW"
    ACCEPT = "ACCEPT"
    RETURN = "RETURN"
    START = "START"
    UPDATE = "UPDATE"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    COMPLETE = "COMPLETE"
    ASSIGN = "ASSIGN"
    CANCEL = "CANCEL"
    CHANGE_PRIORITY = "CHANGE_PRIORITY"
    QC_REVIEW = "QC_REVIEW"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    code: str = "TASK_ACCESS_DENIED"
    message: str = "Bạn không có quyền thực hiện thao tác này."


def is_active_user(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and user.is_active
        and not getattr(user, "is_deleted", False)
    )


def active_memberships(user):
    if not is_active_user(user):
        return BranchMembership.objects.none()
    return BranchMembership.objects.filter(user=user, is_active=True).select_related(
        "branch",
        "team",
    ).prefetch_related("areas", "skills")


def membership_for(user, branch_id):
    return active_memberships(user).filter(branch_id=branch_id).first()


def is_branch_owner(user, branch):
    """Ownership comes from the branch relation, never from the account role alone."""
    return bool(is_active_user(user) and getattr(branch, "owner_id", None) == user.id)


def can_view_booking_guest(user, branch):
    if not is_active_user(user):
        return False
    if user.role in GLOBAL_ROLES or is_branch_owner(user, branch):
        return True
    membership = membership_for(user, branch.id)
    if membership is None:
        return False
    return bool(
        membership.membership_role
        in {
            BranchMembership.MembershipRole.MANAGER,
            BranchMembership.MembershipRole.SALES,
        }
        or user.role in {
            User.Role.MANAGER,
            User.Role.CUSTOMER_SERVICE,
            User.Role.SALES,
        }
    )


def allowed_branch_ids(user):
    if not is_active_user(user):
        return []
    if user.role in GLOBAL_ROLES:
        return None
    return list(active_memberships(user).values_list("branch_id", flat=True))


def _membership_area_ids(membership):
    area_ids = set(membership.areas.values_list("id", flat=True))
    return area_ids


def membership_covers_task(membership, task):
    if membership.branch_id != task.branch_id:
        return False
    role = membership.membership_role
    if role in {
        BranchMembership.MembershipRole.MANAGER,
        BranchMembership.MembershipRole.QC,
        BranchMembership.MembershipRole.WAREHOUSE,
        BranchMembership.MembershipRole.TECHNICIAN,
        BranchMembership.MembershipRole.SALES,
        BranchMembership.MembershipRole.VIEWER,
    }:
        return True

    area_ids = _membership_area_ids(membership)
    task_area_id = task.area_id or getattr(task.room, "area_ref_id", None)
    if area_ids and task_area_id not in area_ids:
        return False
    if not area_ids and membership.area:
        task_area_name = getattr(task.room, "area", "")
        if task_area_name and task_area_name != membership.area:
            return False
    if membership.team_id and task.team_id and membership.team_id != task.team_id:
        return False
    return True


def membership_has_task_skills(membership, task):
    """Return true only when the worker owns every skill required by the task."""
    required_skill_ids = set(task.required_skills.values_list("id", flat=True))
    if not required_skill_ids:
        return True
    worker_skill_ids = set(membership.skills.values_list("id", flat=True))
    return required_skill_ids.issubset(worker_skill_ids)


def _skill_qualified_task_ids(membership):
    skill_ids = list(membership.skills.values_list("id", flat=True))
    queryset = HousekeepingTask.objects.filter(branch_id=membership.branch_id)
    if not skill_ids:
        return queryset.filter(required_skills__isnull=True).values("pk")
    return (
        queryset
        .annotate(
            required_skill_count=Count("required_skills", distinct=True),
            matched_skill_count=Count(
                "required_skills",
                filter=Q(required_skills__in=skill_ids),
                distinct=True,
            ),
        )
        .filter(required_skill_count=F("matched_skill_count"))
        .values("pk")
    )


def user_is_on_task_shift(user, task, *, at=None):
    if task.shift_id is None:
        return True
    at = at or timezone.now()
    if ShiftAssignment.objects.filter(user=user, shift_id=task.shift_id, is_active=True).exists():
        return task.shift.contains(at)
    has_explicit_schedule = ShiftAssignment.objects.filter(
        user=user,
        shift__branch_id=task.branch_id,
        is_active=True,
    ).exists()
    if has_explicit_schedule:
        return False
    # Compatibility for legacy memberships until every roster has explicit rows.
    return task.shift.contains(at)


def can_work_outside_shift(user, task, membership=None):
    if user.role in GLOBAL_ROLES:
        return True
    membership = membership or membership_for(user, task.branch_id)
    if membership is None:
        return False
    if membership.can_work_outside_shift:
        return True
    try:
        policy_allows = task.branch.housekeeping_policy.allow_work_outside_shift
    except AttributeError:
        policy_allows = False
    return bool(policy_allows and task.priority == HousekeepingTask.Priority.URGENT)


def _management_membership(membership):
    return membership and membership.membership_role == BranchMembership.MembershipRole.MANAGER


def _lead_membership(membership):
    return membership and membership.membership_role == BranchMembership.MembershipRole.HOUSEKEEPING_LEAD


def _qc_membership(membership):
    return membership and membership.membership_role == BranchMembership.MembershipRole.QC


def decide_task_capability(user, task, capability):
    if not is_active_user(user):
        return PermissionDecision(False)
    if user.role in GLOBAL_ROLES:
        return PermissionDecision(True)

    membership = membership_for(user, task.branch_id)
    if membership is None:
        return PermissionDecision(
            False,
            "USER_BRANCH_NOT_ALLOWED",
            "Bạn không có quyền tại chi nhánh này.",
        )
    if not membership_covers_task(membership, task):
        return PermissionDecision(False)

    is_manager = is_branch_owner(user, task.branch) or _management_membership(membership)
    is_lead = _lead_membership(membership)
    is_qc = user.role == User.Role.QC or _qc_membership(membership)
    is_sales = membership.membership_role == BranchMembership.MembershipRole.SALES
    is_owner = task.assignee_id == user.id

    if capability == Capability.VIEW:
        if is_manager or is_lead or is_qc or is_sales:
            return PermissionDecision(True)
        if user.role == User.Role.HOUSEKEEPING:
            is_open = task.assignee_id is None and task.status == HousekeepingTask.Status.UNASSIGNED
            return PermissionDecision(is_owner or is_open)
        return PermissionDecision(False)

    if capability == Capability.ACCEPT:
        if user.role != User.Role.HOUSEKEEPING and not is_lead:
            return PermissionDecision(False)
        if task.assignee_id not in {None, user.id}:
            return PermissionDecision(False, "TASK_ALREADY_ASSIGNED", "Công việc đã được nhân viên khác nhận.")
        if not membership_has_task_skills(membership, task):
            return PermissionDecision(
                False,
                "TASK_SKILL_NOT_ALLOWED",
                "Bạn chưa có đủ kỹ năng bắt buộc của task.",
            )
        if not user_is_on_task_shift(user, task) and not can_work_outside_shift(user, task, membership):
            return PermissionDecision(False, "USER_NOT_ON_SHIFT", "Bạn không trong ca làm việc của task.")
        return PermissionDecision(True)

    if capability in {
        Capability.RETURN,
        Capability.START,
        Capability.UPDATE,
        Capability.PAUSE,
        Capability.RESUME,
        Capability.COMPLETE,
    }:
        if is_owner or is_manager:
            return PermissionDecision(True)
        return PermissionDecision(False, message="Bạn không phải người thực hiện task.")

    if capability == Capability.ASSIGN:
        return PermissionDecision(is_manager or is_lead)
    if capability in {Capability.CANCEL, Capability.CHANGE_PRIORITY}:
        return PermissionDecision(is_manager)
    if capability == Capability.QC_REVIEW:
        return PermissionDecision(is_qc or is_manager)
    return PermissionDecision(False)


def open_task_scope_q(membership, user):
    scope = Q(branch_id=membership.branch_id)
    role = membership.membership_role
    if role in {
        BranchMembership.MembershipRole.MANAGER,
        BranchMembership.MembershipRole.QC,
        BranchMembership.MembershipRole.SALES,
    }:
        return scope
    if role == BranchMembership.MembershipRole.HOUSEKEEPING_LEAD:
        scoped = Q()
        if membership.team_id:
            scoped |= Q(team_id=membership.team_id)
        area_ids = list(membership.areas.values_list("id", flat=True))
        if area_ids:
            scoped |= Q(area_id__in=area_ids) | Q(area__isnull=True, room__area_ref_id__in=area_ids)
        if not scoped:
            scoped = Q()
        return scope & scoped
    if role == BranchMembership.MembershipRole.HOUSEKEEPER:
        open_scope = Q(assignee=user)
        eligible_open = Q(assignee__isnull=True, status=HousekeepingTask.Status.UNASSIGNED)
        eligible_open &= Q(pk__in=_skill_qualified_task_ids(membership))
        if membership.team_id:
            eligible_open &= Q(team_id=membership.team_id) | Q(team__isnull=True)
        area_ids = list(membership.areas.values_list("id", flat=True))
        if area_ids:
            eligible_open &= Q(area_id__in=area_ids) | Q(area__isnull=True, room__area_ref_id__in=area_ids)
        elif membership.area:
            eligible_open &= Q(room__area=membership.area)
        return scope & (open_scope | eligible_open)
    return scope & Q(pk__in=[])
