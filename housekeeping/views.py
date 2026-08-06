"""Session-authenticated Housekeeping backoffice views.

The versioned JSON API lives in ``housekeeping.api`` so HTTP contracts do not
leak into the template layer.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.models import User

from .api.query import filtered_task_queryset, task_for_detail
from .dashboard import build_performance_dashboard, build_sla_dashboard
from .models import (
    Area,
    Booking,
    Branch,
    BranchMembership,
    ChecklistVersion,
    HousekeepingActivityLog,
    HousekeepingTeam,
    HousekeepingTask,
    IssueTicket,
    NotificationRecipient,
    Room,
    Shift,
    Skill,
    SupplyRequest,
)
from .notifications import mark_notification_read
from .selectors import task_queryset_for_user
from .services import (
    HousekeepingError,
    accept_task,
    cancel_task,
    change_task_priority,
    complete_task,
    create_task,
    create_supply_request,
    pause_task,
    reassign_task,
    record_task_view,
    report_issue,
    request_context,
    resume_task,
    return_task,
    review_qc,
    scoped_issues,
    scoped_supply_requests,
    start_task,
    update_checklist_item,
    update_issue_status,
    update_supply_request_status,
    update_task_note,
    upload_task_photo,
)


MANAGEMENT_ROLES = {User.Role.FOUNDER, User.Role.MANAGER}


def _allowed_branches(user):
    branches = Branch.objects.filter(is_active=True)
    if user.role != User.Role.FOUNDER:
        allowed_ids = user.branch_memberships.filter(is_active=True).values_list("branch_id", flat=True)
        branches = branches.filter(id__in=allowed_ids)
    return branches


@login_required
def task_list(request):
    try:
        tasks = filtered_task_queryset(request.user, request.GET)
        branches = _allowed_branches(request.user)
        shifts = Shift.objects.filter(is_active=True, branch__in=branches).select_related(
            "branch"
        ).order_by("branch__name", "starts_at", "name")
        return render(
            request,
            "housekeeping/task_list.html",
            {
                "tasks": tasks,
                "branches": branches,
                "shifts": shifts,
                "selected_date": request.GET.get("date") or timezone.localdate().isoformat(),
                "statuses": HousekeepingTask.Status.choices,
                "task_types": HousekeepingTask.TaskType.choices,
                "priorities": HousekeepingTask.Priority.choices,
            },
        )
    except HousekeepingError as error:
        messages.error(request, error.message)
        return redirect("dashboard")


@login_required
@require_http_methods(["GET", "POST"])
def task_create(request):
    branches = _allowed_branches(request.user)
    can_create = request.user.role in MANAGEMENT_ROLES
    if not can_create:
        messages.error(request, "Bạn không có quyền tạo công việc.")
        return redirect("housekeeping:task-list")
    if request.method == "POST":
        try:
            task = create_task(
                request.user,
                {
                    "code": request.POST.get("code"),
                    "branchId": request.POST.get("branchId"),
                    "roomId": request.POST.get("roomId"),
                    "bookingId": request.POST.get("bookingId") or None,
                    "taskType": request.POST.get("taskType"),
                    "priority": request.POST.get("priority"),
                    "assigneeId": request.POST.get("assigneeId") or None,
                    "shiftId": request.POST.get("shiftId") or None,
                    "teamId": request.POST.get("teamId") or None,
                    "areaId": request.POST.get("areaId") or None,
                    "checklistVersionId": request.POST.get("checklistVersionId") or None,
                    "requiredSkillIds": request.POST.getlist("requiredSkillIds"),
                    "scheduledStartAt": request.POST.get("scheduledStartAt"),
                    "dueAt": request.POST.get("dueAt"),
                    "nextCheckinAt": request.POST.get("nextCheckinAt") or None,
                    "standardDurationMinutes": request.POST.get("standardDurationMinutes") or None,
                    "requiresQc": request.POST.get("requiresQc") == "on",
                    "guestInRoom": request.POST.get("guestInRoom") == "on",
                    "specialRequest": request.POST.get("specialRequest"),
                    "note": request.POST.get("note"),
                    "source": "MANUAL_BACKOFFICE",
                },
                request_context(request),
            )
        except HousekeepingError as error:
            messages.error(request, error.message)
        else:
            messages.success(request, f"Đã tạo công việc {task.code}.")
            return redirect("housekeeping:task-detail", task_id=task.id)
    branch_ids = branches.values("id")
    return render(
        request,
        "housekeeping/task_create.html",
        {
            "branches": branches,
            "rooms": Room.objects.filter(branch_id__in=branch_ids).select_related("branch").order_by("branch__name", "code"),
            "bookings": Booking.objects.filter(branch_id__in=branch_ids).select_related("branch", "room").order_by("branch__name", "code"),
            "shifts": Shift.objects.filter(branch_id__in=branch_ids, is_active=True).select_related("branch"),
            "areas": Area.objects.filter(branch_id__in=branch_ids, is_active=True).select_related("branch"),
            "teams": HousekeepingTeam.objects.filter(branch_id__in=branch_ids, is_active=True).select_related("branch"),
            "skills": Skill.objects.filter(Q(branch_id__in=branch_ids) | Q(branch__isnull=True), is_active=True),
            "checklist_versions": ChecklistVersion.objects.filter(
                status=ChecklistVersion.Status.PUBLISHED,
                template__is_active=True,
            ).filter(Q(template__branch_id__in=branch_ids) | Q(template__branch__isnull=True)).select_related("template"),
            "assignees": User.objects.filter(
                role=User.Role.HOUSEKEEPING,
                is_active=True,
                is_deleted=False,
                branch_memberships__branch_id__in=branch_ids,
                branch_memberships__is_active=True,
            ).distinct().order_by("first_name", "last_name", "username"),
            "task_types": HousekeepingTask.TaskType.choices,
            "priorities": HousekeepingTask.Priority.choices,
            "default_start": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
            "default_due": (timezone.localtime() + timedelta(minutes=45)).strftime("%Y-%m-%dT%H:%M"),
        },
    )


@login_required
def task_detail(request, task_id):
    try:
        task = task_for_detail(request.user, task_id)
    except HousekeepingError as error:
        messages.error(request, error.message)
        return redirect("housekeeping:task-list")
    record_task_view(task, request.user, request_context(request))
    return render(
        request,
        "housekeeping/task_detail.html",
        {
            "task": task,
            "is_management": request.user.role in {User.Role.FOUNDER, User.Role.MANAGER},
            "can_qc": request.user.role in {User.Role.FOUNDER, User.Role.MANAGER, User.Role.QC},
            "assignees": User.objects.filter(
                role=User.Role.HOUSEKEEPING,
                is_active=True,
                is_deleted=False,
                branch_memberships__branch=task.branch,
                branch_memberships__is_active=True,
            ).distinct().order_by("first_name", "last_name", "username"),
        },
    )


@login_required
def operations_dashboard(request):
    try:
        params = request.GET.copy()
        if not any(params.get(key) for key in ("date", "dateFrom", "dateTo")):
            params["date"] = timezone.localdate().isoformat()
        tasks = filtered_task_queryset(request.user, params, apply_defaults=False)
        sla = build_sla_dashboard(tasks)
        performance = build_performance_dashboard(tasks)
        status_counts = list(
            tasks.values("status").annotate(total=Count("id")).order_by("status")
        )
        qc_tasks = list(
            tasks.filter(
                status__in={HousekeepingTask.Status.WAITING_QC, HousekeepingTask.Status.QC_REJECTED}
            )[:50]
        )
        active_tasks = list(
            tasks.filter(
                status__in={
                    HousekeepingTask.Status.ACCEPTED,
                    HousekeepingTask.Status.IN_PROGRESS,
                    HousekeepingTask.Status.PAUSED,
                    HousekeepingTask.Status.WAITING_SUPPORT,
                }
            )[:100]
        )
    except HousekeepingError as error:
        messages.error(request, error.message)
        return redirect("housekeeping:task-list")
    return render(
        request,
        "housekeeping/operations_dashboard.html",
        {
            "sla": sla,
            "performance": performance,
            "status_counts": status_counts,
            "qc_tasks": qc_tasks,
            "active_tasks": active_tasks,
            "branches": _allowed_branches(request.user),
            "selected_date": params.get("date", ""),
            "is_management": request.user.role in MANAGEMENT_ROLES
            or request.user.branch_memberships.filter(
                is_active=True,
                membership_role=BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
            ).exists(),
        },
    )


@login_required
def support_queue(request):
    supplies = SupplyRequest.objects.none()
    issues = IssueTicket.objects.none()
    supply_denied = issue_denied = False
    try:
        supplies = scoped_supply_requests(request.user)
        if request.GET.get("supplyStatus"):
            supplies = supplies.filter(status=request.GET["supplyStatus"])
        supplies = supplies.order_by("status", "-created_at")[:100]
    except HousekeepingError:
        supply_denied = True
    try:
        issues = scoped_issues(request.user)
        if request.GET.get("issueStatus"):
            issues = issues.filter(status=request.GET["issueStatus"])
        issues = issues.order_by("status", "-created_at")[:100]
    except HousekeepingError:
        issue_denied = True
    if supply_denied and issue_denied:
        messages.error(request, "Bạn không có quyền xem hàng đợi Kho hoặc Kỹ thuật.")
        return redirect("housekeeping:task-list")
    return render(
        request,
        "housekeeping/support_queue.html",
        {
            "supplies": supplies,
            "issues": issues,
            "supply_statuses": SupplyRequest.Status.choices,
            "issue_statuses": IssueTicket.Status.choices,
            "supply_denied": supply_denied,
            "issue_denied": issue_denied,
        },
    )


@login_required
@require_http_methods(["POST"])
def support_web_action(request, entity_type, entity_id):
    try:
        if entity_type == "supply":
            update_supply_request_status(
                request.user,
                entity_id,
                request.POST.get("version"),
                request.POST.get("status"),
                request.POST.get("note"),
                request_context(request),
            )
        elif entity_type == "issue":
            update_issue_status(
                request.user,
                entity_id,
                request.POST.get("version"),
                request.POST.get("status"),
                request.POST.get("note"),
                request_context(request),
                assigned_to_id=request.POST.get("assignedToId") or None,
            )
        else:
            raise HousekeepingError("SYSTEM_ERROR", "Loại hàng đợi không hợp lệ.")
    except HousekeepingError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, "Đã cập nhật hàng đợi hỗ trợ.")
    return redirect("housekeeping:support-queue")


@login_required
def activity_log(request):
    task_ids = task_queryset_for_user(request.user).values("id")
    logs = HousekeepingActivityLog.objects.filter(task_id__in=task_ids).select_related(
        "task", "task__room", "branch", "user"
    )
    if request.GET.get("action"):
        logs = logs.filter(action=request.GET["action"])
    query = request.GET.get("q", "").strip()
    if query:
        logs = logs.filter(
            Q(task__code__icontains=query)
            | Q(task__room__code__icontains=query)
            | Q(correlation_id__icontains=query)
            | Q(user__username__icontains=query)
        )
    actions = HousekeepingActivityLog.objects.filter(task_id__in=task_ids).values_list(
        "action", flat=True
    ).distinct().order_by("action")
    return render(
        request,
        "housekeeping/activity_log.html",
        {"logs": logs[:250], "actions": actions},
    )


@login_required
def notification_center(request):
    notifications = NotificationRecipient.objects.filter(user=request.user).select_related(
        "notification", "notification__task", "notification__task__room", "notification__branch"
    )
    if request.GET.get("unread") == "true":
        notifications = notifications.filter(read_at__isnull=True)
    return render(
        request,
        "housekeeping/notification_center.html",
        {
            "notifications": notifications.order_by("-notification__created_at")[:100],
            "unread_count": NotificationRecipient.objects.filter(
                user=request.user, read_at__isnull=True
            ).count(),
        },
    )


@login_required
@require_http_methods(["POST"])
def notification_web_read(request, recipient_id):
    if mark_notification_read(request.user, recipient_id) is None:
        messages.error(request, "Không tìm thấy thông báo.")
    return redirect("housekeeping:notification-center")


@login_required
@require_http_methods(["POST"])
def task_web_action(request, task_id, action):
    try:
        context = request_context(request)
        version = request.POST.get("version")
        if action == "accept":
            accept_task(request.user, task_id, version, context)
        elif action == "start":
            start_task(request.user, task_id, version, context)
        elif action == "return":
            return_task(
                request.user,
                task_id,
                version,
                request.POST.get("reasonCode"),
                request.POST.get("note"),
                context,
            )
        elif action == "pause":
            pause_task(
                request.user,
                task_id,
                version,
                request.POST.get("reasonCode"),
                request.POST.get("note"),
                context,
            )
        elif action == "resume":
            resume_task(request.user, task_id, version, context)
        elif action == "complete":
            complete_task(
                request.user,
                task_id,
                version,
                request.POST.get("confirmFinalInspection") == "on",
                request.POST.get("finalNote"),
                context,
            )
        elif action == "checklist":
            update_checklist_item(
                request.user,
                task_id,
                request.POST.get("itemId"),
                {
                    "version": version,
                    "status": request.POST.get("status"),
                    "value": request.POST.get("value") or True,
                    "note": request.POST.get("note"),
                },
                context,
            )
        elif action == "photo":
            image = request.FILES.get("image")
            if image is None:
                raise HousekeepingError("REQUIRED_PHOTO_MISSING", "Vui lòng chọn ảnh tải lên.")
            upload_task_photo(request.user, task_id, image, request.POST, context)
        elif action == "note":
            update_task_note(
                request.user,
                task_id,
                version,
                request.POST.get("note"),
                context,
            )
        elif action == "supply":
            create_supply_request(
                request.user,
                task_id,
                {
                    "version": version,
                    "items": [
                        {
                            "inventoryItemId": request.POST.get("inventoryItemId"),
                            "name": request.POST.get("itemName"),
                            "quantity": request.POST.get("quantity"),
                            "unit": request.POST.get("unit"),
                        }
                    ],
                    "priority": request.POST.get("priority"),
                    "note": request.POST.get("note"),
                    "clientRequestId": request.POST.get("clientRequestId"),
                },
                context,
            )
        elif action == "issue":
            report_issue(
                request.user,
                task_id,
                {
                    "version": version,
                    "deviceId": request.POST.get("deviceId"),
                    "issueType": request.POST.get("issueType"),
                    "severity": request.POST.get("severity"),
                    "description": request.POST.get("description"),
                    "blocksRoomReady": request.POST.get("blocksRoomReady") == "on",
                    "clientRequestId": request.POST.get("clientRequestId"),
                },
                context,
            )
        elif action == "qc-approve":
            review_qc(request.user, task_id, version, True, "", request.POST.get("note"), context)
        elif action == "qc-reject":
            failed_items = [
                {
                    "checklistItemId": item_id,
                    "reasonCode": request.POST.get(f"reasonCode_{item_id}") or "QC_FAILED",
                    "reason": request.POST.get(f"reason_{item_id}") or request.POST.get("reason"),
                    "note": request.POST.get(f"note_{item_id}") or "",
                    "reworkRequired": True,
                }
                for item_id in request.POST.getlist("failedItemIds")
            ]
            review_qc(
                request.user,
                task_id,
                version,
                False,
                request.POST.get("reason"),
                request.POST.get("note"),
                context,
                failed_items=failed_items,
                deadline_at=request.POST.get("deadlineAt") or None,
            )
        elif action == "reassign":
            reassign_task(
                request.user,
                task_id,
                request.POST.get("assigneeId"),
                version,
                context,
                reason_code=request.POST.get("reasonCode") or "MANAGER_REASSIGN",
                note=request.POST.get("note") or "",
            )
        elif action == "priority":
            change_task_priority(
                request.user,
                task_id,
                version,
                request.POST.get("priority"),
                request.POST.get("reason"),
                context,
            )
        elif action == "cancel":
            cancel_task(
                request.user,
                task_id,
                version,
                request.POST.get("reason"),
                context,
            )
        else:
            raise HousekeepingError("SYSTEM_ERROR", "Thao tác không hợp lệ.")
    except HousekeepingError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, "Cập nhật công việc thành công.")
    return redirect("housekeeping:task-detail", task_id=task_id)
