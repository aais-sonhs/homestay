import uuid
from datetime import date, timedelta

from django.db.models import Count, F, Q
from django.utils import timezone

from accounts.models import User
from housekeeping.models import HousekeepingTask, TaskChecklistItem
from housekeeping.selectors import prioritized_task_queryset, task_queryset_for_user
from housekeeping.services import HousekeepingError
from organizations.models import ShiftAssignment


TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_true(value):
    return str(value or "").lower() in TRUE_VALUES


def _csv(params, name):
    values = []
    for raw_value in params.getlist(name):
        values.extend(value.strip() for value in raw_value.split(",") if value.strip())
    return values


def _filter_identifier(queryset, value, *, id_field, code_field=None, name_field=None):
    try:
        return queryset.filter(**{id_field: uuid.UUID(str(value))})
    except ValueError:
        lookup = Q()
        if code_field:
            lookup |= Q(**{code_field: value})
        if name_field:
            lookup |= Q(**{name_field: value})
        return queryset.filter(lookup) if lookup else queryset.none()


def filtered_task_queryset(user, params, *, apply_defaults=True):
    queryset = prioritized_task_queryset(user)
    tab = params.get("tab", "").lower()
    requested_date = params.get("date")
    if requested_date:
        try:
            selected_date = date.fromisoformat(requested_date)
        except ValueError:
            raise HousekeepingError("SYSTEM_ERROR", "Ngày lọc không hợp lệ.") from None
        queryset = queryset.filter(scheduled_start_at__date=selected_date)
    elif params.get("dateFrom") or params.get("dateTo"):
        try:
            date_from = date.fromisoformat(params["dateFrom"]) if params.get("dateFrom") else None
            date_to = date.fromisoformat(params["dateTo"]) if params.get("dateTo") else None
        except ValueError:
            raise HousekeepingError("SYSTEM_ERROR", "Khoảng ngày lọc không hợp lệ.") from None
        if date_from and date_to and date_from > date_to:
            raise HousekeepingError("SYSTEM_ERROR", "Ngày bắt đầu phải trước ngày kết thúc.")
        if date_from:
            queryset = queryset.filter(scheduled_start_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_start_at__date__lte=date_to)
    elif apply_defaults:
        queryset = queryset.filter(scheduled_start_at__date=timezone.localdate())

    shift_id = params.get("shiftId") or params.get("shift")
    if shift_id:
        queryset = _filter_identifier(queryset, shift_id, id_field="shift_id", code_field="shift__code")
    elif apply_defaults:
        now = timezone.now()
        assigned_shift_ids = list(
            ShiftAssignment.objects.filter(
                user=user,
                is_active=True,
                shift__is_active=True,
                shift__starts_at__lte=now,
                shift__ends_at__gte=now,
            ).values_list("shift_id", flat=True)
        )
        if assigned_shift_ids:
            queryset = queryset.filter(Q(shift_id__in=assigned_shift_ids) | Q(shift__isnull=True))
        else:
            queryset = queryset.filter(
                Q(shift__starts_at__lte=now, shift__ends_at__gte=now) | Q(shift__isnull=True)
            )

    branch_id = params.get("branchId") or params.get("branch")
    if branch_id:
        queryset = _filter_identifier(queryset, branch_id, id_field="branch_id", code_field="branch__code")

    statuses = _csv(params, "status")
    if statuses:
        invalid = sorted(set(statuses) - set(HousekeepingTask.Status.values))
        if invalid:
            raise HousekeepingError("SYSTEM_ERROR", "Trạng thái lọc không hợp lệ.", details={"values": invalid})
        queryset = queryset.filter(status__in=statuses)
    elif apply_defaults and tab != "done":
        queryset = queryset.exclude(
            status__in={HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED}
        )

    task_types = _csv(params, "taskType") or _csv(params, "type")
    if task_types:
        queryset = queryset.filter(task_type__in=task_types)
    priorities = _csv(params, "priority")
    if priorities:
        queryset = queryset.filter(priority__in=priorities)

    assignee = params.get("assignee")
    if assignee == "me":
        queryset = queryset.filter(assignee=user)
    elif assignee == "unassigned":
        queryset = queryset.filter(assignee__isnull=True)
    elif assignee:
        queryset = _filter_identifier(queryset, assignee, id_field="assignee_id", code_field="assignee__username")

    if _is_true(params.get("overdue")):
        queryset = queryset.filter(due_at__lt=timezone.now()).exclude(
            status__in={HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED}
        )

    area = params.get("area") or params.get("areaId")
    if area:
        try:
            area_uuid = uuid.UUID(str(area))
            queryset = queryset.filter(Q(area_id=area_uuid) | Q(area__isnull=True, room__area_ref_id=area_uuid))
        except ValueError:
            queryset = queryset.filter(
                Q(area__code=area) | Q(area__name=area) | Q(area__isnull=True, room__area=area)
            )
    if params.get("floor"):
        queryset = queryset.filter(room__floor=params["floor"])
    if params.get("roomType"):
        queryset = queryset.filter(room__room_type=params["roomType"])
    if _is_true(params.get("qcRework")):
        queryset = queryset.filter(status=HousekeepingTask.Status.QC_REJECTED)
    if _is_true(params.get("checkinRisk")):
        now = timezone.now()
        queryset = queryset.filter(next_checkin_at__isnull=False).filter(
            Q(next_checkin_at__lte=now + timedelta(hours=1)) | Q(due_at__gte=F("next_checkin_at"))
        )

    if tab == "mine":
        queryset = queryset.filter(assignee=user)
    elif tab == "open":
        queryset = queryset.filter(assignee__isnull=True, status=HousekeepingTask.Status.UNASSIGNED)
    elif tab == "in-progress":
        queryset = queryset.filter(status=HousekeepingTask.Status.IN_PROGRESS)
    elif tab == "support":
        queryset = queryset.filter(
            status__in={HousekeepingTask.Status.PAUSED, HousekeepingTask.Status.WAITING_SUPPORT}
        )
    elif tab == "waiting-qc":
        queryset = queryset.filter(status=HousekeepingTask.Status.WAITING_QC)
    elif tab == "qc-rework":
        queryset = queryset.filter(status=HousekeepingTask.Status.QC_REJECTED)
    elif tab == "done":
        queryset = queryset.filter(
            status__in={HousekeepingTask.Status.COMPLETED, HousekeepingTask.Status.QC_APPROVED}
        )

    query = params.get("q", "").strip()
    if query:
        search = (
            Q(code__icontains=query)
            | Q(room__code__icontains=query)
            | Q(room__name__icontains=query)
            | Q(booking_code__icontains=query)
            | Q(booking__code__icontains=query)
        )
        if user.role in {User.Role.FOUNDER, User.Role.MANAGER, User.Role.CUSTOMER_SERVICE}:
            search |= Q(booking__guest_name__icontains=query) | Q(booking__guest_phone__icontains=query)
        queryset = queryset.filter(search)

    return queryset.annotate(
        api_required_count=Count(
            "checklist_items",
            filter=Q(checklist_items__is_required=True),
            distinct=True,
        ),
        api_completed_required_count=Count(
            "checklist_items",
            filter=Q(
                checklist_items__is_required=True,
                checklist_items__status=TaskChecklistItem.Status.COMPLETED,
            ),
            distinct=True,
        ),
        api_photo_count=Count("photos", distinct=True),
    )


def task_for_detail(user, task_id):
    try:
        return (
            task_queryset_for_user(user)
            .select_related("sla_state", "sla_state__policy")
            .prefetch_related(
                "checklist_items__completed_by",
                "checklist_items__failure_accepted_by",
                "checklist_items__photos",
                "photos__uploaded_by",
                "issues__reported_by",
                "supply_requests__items",
                "qc_rounds__reviewer",
                "qc_rounds__failed_items__checklist_item",
                "qc_rounds__photos__uploaded_by",
                "rework_rounds__source_qc_round",
                "rework_rounds__started_by",
                "assignments__assignee",
                "assignments__assigned_by",
                "handovers__from_user",
                "handovers__to_user",
                "room_verifications__user",
                "pauses",
                "status_history__changed_by",
            )
            .get(pk=task_id)
        )
    except (HousekeepingTask.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy công việc.", status=404) from None
