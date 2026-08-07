from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    BranchMembership,
    BranchHousekeepingPolicy,
    HousekeepingTask,
    SLAPolicy,
    SupplyLocation,
)

from .models import Branch, BranchOwnershipHistory


class BranchOperationError(Exception):
    pass


def _validate_owner(owner):
    if owner is None or not owner.is_active or owner.is_deleted:
        raise BranchOperationError("Vui lòng chọn một tài khoản chủ chi nhánh đang hoạt động.")


def _activate_owner_membership(branch, owner):
    BranchMembership.objects.update_or_create(
        branch=branch,
        user=owner,
        defaults={
            "is_active": True,
            "membership_role": BranchMembership.MembershipRole.MANAGER,
            "can_manage_team": True,
        },
    )


def _deactivate_previous_owner_membership(branch, previous_owner_id):
    if not previous_owner_id:
        return
    BranchMembership.objects.filter(
        branch=branch,
        user_id=previous_owner_id,
        user__role=User.Role.BRANCH_OWNER,
    ).update(is_active=False)


@transaction.atomic
def assign_branches_to_owner(*, owner, branches, changed_by=None):
    """Assign or transfer selected branches to one owner with audit and memberships."""
    _validate_owner(owner)
    branch_ids = {branch.pk for branch in branches}
    if not branch_ids:
        return 0
    locked_branches = list(
        Branch.objects.select_for_update().filter(pk__in=branch_ids).order_by("pk")
    )
    if len(locked_branches) != len(branch_ids):
        raise BranchOperationError("Có chi nhánh không còn tồn tại. Vui lòng tải lại trang.")

    transferred = 0
    for branch in locked_branches:
        previous_owner_id = branch.owner_id
        if previous_owner_id == owner.pk:
            _activate_owner_membership(branch, owner)
            continue
        branch.owner = owner
        branch.save(update_fields=("owner",))
        _activate_owner_membership(branch, owner)
        _deactivate_previous_owner_membership(branch, previous_owner_id)
        BranchOwnershipHistory.objects.create(
            branch=branch,
            previous_owner_id=previous_owner_id,
            new_owner=owner,
            changed_by=changed_by,
            source=BranchOwnershipHistory.Source.TRANSFERRED,
        )
        transferred += 1
    return transferred


@transaction.atomic
def create_branch(*, code, name, owner, address="", changed_by=None):
    _validate_owner(owner)
    branch = Branch.objects.create(code=code, name=name, address=address, owner=owner, is_active=True)
    BranchOwnershipHistory.objects.create(
        branch=branch,
        new_owner=owner,
        changed_by=changed_by,
        source=BranchOwnershipHistory.Source.CREATED,
    )
    _activate_owner_membership(branch, owner)
    BranchHousekeepingPolicy.objects.get_or_create(branch=branch)
    SupplyLocation.objects.get_or_create(
        branch=branch,
        code="DEFAULT",
        defaults={"name": "Kho mặc định", "is_active": True},
    )
    SLAPolicy.objects.get_or_create(
        branch=branch,
        name="Thời hạn buồng phòng mặc định",
        task_type="",
        priority="",
        defaults={"is_active": True},
    )
    return branch


@transaction.atomic
def update_branch(branch, *, code, name, owner, address="", changed_by=None):
    _validate_owner(owner)
    locked = Branch.objects.select_for_update().get(pk=branch.pk)
    previous_owner_id = locked.owner_id
    locked.code = code
    locked.name = name
    locked.address = address
    locked.owner = owner
    locked.save(update_fields=("code", "name", "address", "owner"))
    _activate_owner_membership(locked, owner)
    if previous_owner_id and previous_owner_id != owner.pk:
        _deactivate_previous_owner_membership(locked, previous_owner_id)
        BranchOwnershipHistory.objects.create(
            branch=locked,
            previous_owner_id=previous_owner_id,
            new_owner=owner,
            changed_by=changed_by,
            source=BranchOwnershipHistory.Source.TRANSFERRED,
        )
    return locked


@transaction.atomic
def set_branch_active(branch, *, active):
    locked = Branch.objects.select_for_update().get(pk=branch.pk)
    if locked.is_active == active:
        return locked
    if not active:
        active_task_exists = locked.housekeeping_tasks.exclude(
            status__in={
                HousekeepingTask.Status.QC_APPROVED,
                HousekeepingTask.Status.CANCELLED,
            }
        ).exists()
        active_booking_exists = locked.bookings.exclude(status=Booking.Status.CANCELLED).filter(
            Q(checkout_at__gte=timezone.now()) | Q(checkout_at__isnull=True)
        ).exists()
        if active_task_exists or active_booking_exists:
            raise BranchOperationError(
                "Không thể ngừng chi nhánh khi còn công việc đang mở hoặc booking chưa kết thúc."
            )
    locked.is_active = active
    locked.save(update_fields=("is_active",))
    return locked
