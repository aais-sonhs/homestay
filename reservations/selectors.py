from django.db.models import Q

from common.access import GLOBAL_ROLES, active_memberships, is_active_user
from housekeeping.models import Booking
from organizations.models import Branch, BranchMembership


BOOKING_CREATOR_MEMBERSHIP_ROLES = {
    BranchMembership.MembershipRole.MANAGER,
    BranchMembership.MembershipRole.SALES,
}

REVENUE_MEMBERSHIP_ROLES = {
    BranchMembership.MembershipRole.MANAGER,
}


def booking_creation_branch_queryset(user):
    queryset = Branch.objects.filter(is_active=True)
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset.order_by("name", "code")
    memberships = active_memberships(user).filter(
        membership_role__in=BOOKING_CREATOR_MEMBERSHIP_ROLES,
    )
    return (
        queryset.filter(Q(owner=user) | Q(memberships__in=memberships))
        .distinct()
        .order_by("name", "code")
    )


def can_create_booking_for_branch(user, branch):
    if not is_active_user(user) or not branch.is_active:
        return False
    if user.role in GLOBAL_ROLES or branch.owner_id == user.id:
        return True
    return active_memberships(user).filter(
        branch=branch,
        membership_role__in=BOOKING_CREATOR_MEMBERSHIP_ROLES,
    ).exists()


def can_create_any_booking(user):
    return booking_creation_branch_queryset(user).exists()


def booking_queryset_for_user(user):
    queryset = Booking.objects.select_related("branch", "room", "created_by").prefetch_related(
        "special_request_items"
    )
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset
    memberships = active_memberships(user)
    return queryset.filter(
        Q(branch__owner=user) | Q(branch__memberships__in=memberships)
    ).distinct()


def revenue_branch_queryset(user):
    """Branches whose financial booking data the user may inspect."""
    queryset = Branch.objects.filter(is_active=True)
    if not is_active_user(user):
        return queryset.none()
    if user.is_superuser or user.role in GLOBAL_ROLES:
        return queryset.order_by("name", "code")
    manager_memberships = active_memberships(user).filter(
        membership_role__in=REVENUE_MEMBERSHIP_ROLES,
    )
    return (
        queryset.filter(Q(owner=user) | Q(memberships__in=manager_memberships))
        .distinct()
        .order_by("name", "code")
    )


def can_view_revenue(user):
    if not is_active_user(user):
        return False
    if user.is_superuser or user.role in GLOBAL_ROLES:
        return True
    return revenue_branch_queryset(user).exists()


def can_manage_revenue_for_branch(user, branch):
    if not getattr(branch, "is_active", False):
        return False
    return revenue_branch_queryset(user).filter(pk=branch.pk).exists()
