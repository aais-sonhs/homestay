"""Read-only query helpers for organizational scope."""

from common.access import GLOBAL_ROLES, active_memberships, is_active_user

from .models import Branch, Room


def branch_queryset_for_user(user):
    queryset = Branch.objects.filter(is_active=True)
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset
    return queryset.filter(memberships__in=active_memberships(user)).distinct()


def room_queryset_for_user(user):
    queryset = Room.objects.select_related("branch", "area_ref")
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset
    return queryset.filter(branch__memberships__in=active_memberships(user)).distinct()

