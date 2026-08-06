from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from accounts.models import User

from .models import HousekeepingTask
from .permissions import GLOBAL_ROLES, active_memberships, is_active_user, open_task_scope_q


def task_queryset_for_user(user):
    queryset = HousekeepingTask.objects.select_related(
        "branch",
        "branch__housekeeping_policy",
        "room",
        "room__area_ref",
        "booking",
        "shift",
        "assignee",
        "assigned_by",
        "updated_by",
        "team",
        "area",
        "checklist_template_version",
    )
    if not is_active_user(user):
        return queryset.none()
    if user.role not in GLOBAL_ROLES:
        memberships = list(active_memberships(user))
        if not memberships:
            return queryset.none()
        combined_scope = None
        for membership in memberships:
            membership_scope = open_task_scope_q(membership, user)
            combined_scope = membership_scope if combined_scope is None else combined_scope | membership_scope
        queryset = queryset.filter(combined_scope).distinct()
    return queryset.prefetch_related("required_skills")


def prioritized_task_queryset(user):
    now = timezone.now()
    return task_queryset_for_user(user).annotate(
        workflow_rank=Case(
            When(status=HousekeepingTask.Status.QC_REJECTED, then=Value(1)),
            When(next_checkin_at__isnull=False, next_checkin_at__gte=now, then=Value(2)),
            When(due_at__lt=now, then=Value(3)),
            When(priority=HousekeepingTask.Priority.URGENT, then=Value(4)),
            When(assignee=user, then=Value(5)),
            default=Value(6),
            output_field=IntegerField(),
        )
    ).order_by("workflow_rank", "next_checkin_at", "due_at", "code", "id")
