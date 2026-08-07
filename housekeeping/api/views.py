import hashlib
import json
import math
import uuid

from django.utils import timezone

from accounts.models import User
from housekeeping.dashboard import build_performance_dashboard, build_sla_dashboard
from common.idempotency import execute_idempotent
from housekeeping.models import (
    Booking,
    GuestServiceRequest,
    HousekeepingTask,
    IssueTicket,
    NotificationRecipient,
    OfflineMutationReceipt,
    SupplyRequest,
)
from housekeeping.guest_requests import (
    CREATOR_ROLES as GUEST_REQUEST_CREATOR_ROLES,
    accept_guest_request,
    assign_guest_request,
    cancel_guest_request,
    complete_guest_request,
    create_guest_request,
    filtered_guest_request_queryset,
    guest_request_for_user,
    start_guest_request,
)
from housekeeping.notifications import mark_notification_read
from housekeeping.selectors import task_queryset_for_user
from housekeeping.services import (
    HousekeepingError,
    accept_checklist_failure,
    accept_task,
    cancel_task,
    change_task_priority,
    complete_task,
    completion_blockers,
    create_task,
    create_supply_request,
    handover_task,
    pause_task,
    reassign_task,
    reject_task,
    report_issue,
    record_task_view,
    request_context,
    resume_task,
    return_task,
    review_qc,
    start_task,
    scoped_issues,
    scoped_supply_requests,
    update_checklist_item,
    upload_task_photo,
    update_issue_status,
    update_supply_request_status,
    update_task_note,
)
from housekeeping.sync import (
    conflict_data,
    discard_conflict,
    discard_failed_receipt,
    process_sync_batch,
    retry_conflict,
)

from .auth import api_authenticated
from .errors import APIError, api_endpoint, parse_json, success_response
from .query import filtered_task_queryset, task_for_detail
from .serializers import (
    guest_request_data,
    issue_data,
    mutation_task_data,
    notification_data,
    supply_request_data,
    task_data,
)
from organizations.models import BranchMembership
from organizations.selectors import branch_queryset_for_user


def _pagination(request):
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
    except ValueError:
        raise APIError("SYSTEM_ERROR", "Thông tin phân trang không hợp lệ.") from None
    if page < 1 or limit < 1 or limit > 100:
        raise APIError(
            "SYSTEM_ERROR",
            "Thông tin phân trang không hợp lệ.",
            details={"pageMin": 1, "limitMin": 1, "limitMax": 100},
        )
    return page, limit


@api_endpoint("GET", "POST")
@api_authenticated
def guest_request_list(request):
    if request.method == "POST":
        payload = parse_json(request)

        def mutate():
            item = create_guest_request(request.user, payload)
            return guest_request_data(item, request.user, detail=True), item.version

        data, replayed, _receipt = execute_idempotent(
            user=request.user,
            task=None,
            idempotency_key=request.headers.get("Idempotency-Key"),
            operation="CREATE_GUEST_REQUEST",
            payload=payload,
            base_version=None,
            mutation=mutate,
        )
        return success_response(
            request,
            data,
            status=200 if replayed else 201,
            replayed=replayed,
        )

    queryset = filtered_guest_request_queryset(request.user, request.GET)
    page, limit = _pagination(request)
    total = queryset.count()
    total_pages = math.ceil(total / limit) if total else 0
    offset = (page - 1) * limit
    items = list(queryset[offset : offset + limit]) if offset < total else []
    return success_response(
        request,
        [guest_request_data(item, request.user) for item in items],
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1 and total > 0,
        },
    )


@api_endpoint("GET")
@api_authenticated
def guest_request_options(request):
    if request.user.role not in GUEST_REQUEST_CREATOR_ROLES:
        raise HousekeepingError(
            "GUEST_REQUEST_ACCESS_DENIED",
            "Bạn không có quyền tạo yêu cầu khách lưu trú.",
            status=403,
        )
    branches = list(branch_queryset_for_user(request.user))
    branch_ids = [branch.id for branch in branches]
    bookings = Booking.objects.select_related("branch", "room").filter(
        branch_id__in=branch_ids,
        status=Booking.Status.CHECKED_IN,
    ).order_by("branch__name", "room__code", "-checkin_at")
    memberships = BranchMembership.objects.select_related("user", "branch").filter(
        branch_id__in=branch_ids,
        is_active=True,
        user__is_active=True,
        user__is_deleted=False,
        user__role=User.Role.HOUSEKEEPING,
        membership_role__in={
            BranchMembership.MembershipRole.HOUSEKEEPER,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        },
    ).order_by("branch__name", "user__first_name", "user__username")
    return success_response(
        request,
        {
            "branches": [
                {"id": str(branch.id), "code": branch.code, "name": branch.name}
                for branch in branches
            ],
            "bookings": [
                {
                    "id": str(booking.id),
                    "code": booking.code,
                    "branchId": str(booking.branch_id),
                    "room": {
                        "id": str(booking.room_id),
                        "code": booking.room.code,
                        "name": booking.room.name,
                    },
                    "guestName": booking.guest_name,
                    "guestPhone": booking.guest_phone,
                }
                for booking in bookings
            ],
            "assignees": [
                {
                    "id": str(membership.user_id),
                    "branchId": str(membership.branch_id),
                    "name": membership.user.display_name,
                }
                for membership in memberships
            ],
            "requestTypes": [
                {"value": value, "label": label}
                for value, label in GuestServiceRequest.RequestType.choices
            ],
            "priorities": [
                {"value": value, "label": label}
                for value, label in GuestServiceRequest.Priority.choices
            ],
            "sources": [
                {"value": value, "label": label}
                for value, label in GuestServiceRequest.Source.choices
            ],
        },
    )


@api_endpoint("GET")
@api_authenticated
def guest_request_detail(request, request_id):
    item = guest_request_for_user(request.user, request_id)
    return success_response(request, guest_request_data(item, request.user, detail=True))


@api_endpoint("POST")
@api_authenticated
def guest_request_action(request, request_id, action):
    payload = parse_json(request)
    operations = {
        "accept": lambda: accept_guest_request(
            request.user, request_id, payload.get("version")
        ),
        "start": lambda: start_guest_request(
            request.user, request_id, payload.get("version")
        ),
        "complete": lambda: complete_guest_request(
            request.user,
            request_id,
            payload.get("version"),
            payload.get("note"),
        ),
        "cancel": lambda: cancel_guest_request(
            request.user,
            request_id,
            payload.get("version"),
            payload.get("reason"),
        ),
        "assign": lambda: assign_guest_request(
            request.user,
            request_id,
            payload.get("assigneeId"),
            payload.get("version"),
            payload.get("note"),
        ),
    }
    if action not in operations:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_ACTION", "Thao tác yêu cầu không hợp lệ.", status=404
        )

    def mutate():
        item = operations[action]()
        return guest_request_data(item, request.user, detail=True), item.version

    data, replayed, _receipt = execute_idempotent(
        user=request.user,
        task=None,
        idempotency_key=request.headers.get("Idempotency-Key"),
        operation=f"GUEST_REQUEST_{action.upper()}",
        payload=payload,
        base_version=payload.get("version"),
        mutation=mutate,
    )
    return success_response(request, data, replayed=replayed)


def _mutation_task(task_id):
    try:
        return HousekeepingTask.objects.only("id", "version").get(pk=task_id)
    except (HousekeepingTask.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy công việc.", status=404) from None


def _require_version(payload):
    if payload.get("version") is None:
        raise APIError(
            "TASK_VERSION_CONFLICT",
            "Thay đổi cần có phiên bản công việc.",
            status=409,
        )


def _run_task_mutation(
    request,
    task_id,
    operation,
    payload,
    callback,
    *,
    status=200,
    client_mutation_id="",
    depends_on=None,
):
    _require_version(payload)
    task_reference = _mutation_task(task_id)
    data, replayed, _receipt = execute_idempotent(
        user=request.user,
        task=task_reference,
        idempotency_key=request.headers.get("Idempotency-Key"),
        operation=operation,
        payload=payload,
        base_version=payload.get("version"),
        mutation=callback,
        client_mutation_id=client_mutation_id,
        depends_on=depends_on,
    )
    return success_response(request, data, status=200 if replayed else status, replayed=replayed)


def _run_entity_mutation(request, task, operation, payload, callback):
    _require_version(payload)
    data, replayed, _receipt = execute_idempotent(
        user=request.user,
        task=task,
        idempotency_key=request.headers.get("Idempotency-Key"),
        operation=operation,
        payload=payload,
        base_version=payload.get("version"),
        mutation=callback,
    )
    return success_response(request, data, replayed=replayed)


@api_endpoint("GET", "POST")
@api_authenticated
def task_list(request):
    if request.method == "POST":
        payload = parse_json(request)
        context = request_context(request)

        def mutate():
            task = create_task(request.user, payload, context)
            return task_data(task, request.user, detail=True, request=request), task.version

        data, replayed, receipt = execute_idempotent(
            user=request.user,
            task=None,
            idempotency_key=request.headers.get("Idempotency-Key"),
            operation="CREATE_TASK",
            payload=payload,
            base_version=None,
            mutation=mutate,
        )
        if receipt.task_id is None and data.get("taskId"):
            OfflineMutationReceipt.objects.filter(pk=receipt.pk).update(task_id=data["taskId"])
        return success_response(request, data, status=200 if replayed else 201, replayed=replayed)

    queryset = filtered_task_queryset(request.user, request.GET)
    page, limit = _pagination(request)
    total = queryset.count()
    total_pages = math.ceil(total / limit) if total else 0
    offset = (page - 1) * limit
    tasks = list(queryset[offset : offset + limit]) if offset < total else []
    return success_response(
        request,
        [task_data(task, request.user) for task in tasks],
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1 and total > 0,
        },
    )


def _dashboard_queryset(request):
    params = request.GET.copy()
    if not any(params.get(name) for name in ("date", "dateFrom", "dateTo")):
        params["date"] = timezone.localdate().isoformat()
    return filtered_task_queryset(request.user, params, apply_defaults=False)


@api_endpoint("GET")
@api_authenticated
def sla_dashboard(request):
    return success_response(request, build_sla_dashboard(_dashboard_queryset(request)))


@api_endpoint("GET")
@api_authenticated
def performance_dashboard(request):
    return success_response(request, build_performance_dashboard(_dashboard_queryset(request)))


@api_endpoint("GET")
@api_authenticated
def notification_list(request):
    queryset = NotificationRecipient.objects.filter(user=request.user).select_related(
        "notification",
        "notification__branch",
        "notification__task",
    )
    unread = str(request.GET.get("unread", "")).lower()
    if unread in {"1", "true", "yes", "on"}:
        queryset = queryset.filter(read_at__isnull=True)
    elif unread in {"0", "false", "no", "off"}:
        queryset = queryset.filter(read_at__isnull=False)
    if request.GET.get("type"):
        queryset = queryset.filter(notification__notification_type=request.GET["type"])
    if request.GET.get("branchId"):
        try:
            branch_id = uuid.UUID(str(request.GET["branchId"]))
        except ValueError:
            raise APIError("SYSTEM_ERROR", "Chi nhánh lọc thông báo không hợp lệ.") from None
        queryset = queryset.filter(notification__branch_id=branch_id)
    queryset = queryset.order_by("-notification__created_at", "-id")
    page, limit = _pagination(request)
    total = queryset.count()
    unread_count = NotificationRecipient.objects.filter(user=request.user, read_at__isnull=True).count()
    total_pages = math.ceil(total / limit) if total else 0
    offset = (page - 1) * limit
    rows = list(queryset[offset : offset + limit]) if offset < total else []
    return success_response(
        request,
        {"items": [notification_data(row) for row in rows], "unreadCount": unread_count},
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1 and total > 0,
        },
    )


@api_endpoint("POST")
@api_authenticated
def notification_read(request, recipient_id):
    payload = parse_json(request)
    try:
        recipient = NotificationRecipient.objects.select_related("notification").get(
            pk=recipient_id,
            user=request.user,
        )
    except (NotificationRecipient.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy thông báo.", status=404) from None

    def mutate():
        updated = mark_notification_read(request.user, recipient_id)
        if updated is None:
            raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy thông báo.", status=404)
        return {
            "recipientId": str(updated.id),
            "notificationId": str(updated.notification_id),
            "readAt": updated.read_at.isoformat(),
        }, None

    data, replayed, _receipt = execute_idempotent(
        user=request.user,
        task=recipient.notification.task,
        idempotency_key=request.headers.get("Idempotency-Key"),
        operation="READ_NOTIFICATION",
        payload=payload,
        base_version=None,
        mutation=mutate,
    )
    return success_response(request, data, replayed=replayed)


@api_endpoint("GET")
@api_authenticated
def task_detail(request, task_id):
    task = task_for_detail(request.user, task_id)
    record_task_view(task, request.user, request_context(request))
    return success_response(request, task_data(task, request.user, detail=True, request=request))


@api_endpoint("PATCH")
@api_authenticated
def task_note(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        task = update_task_note(
            request.user,
            task_id,
            payload.get("version"),
            payload.get("note"),
            context,
        )
        return mutation_task_data(task), task.version

    return _run_task_mutation(request, task_id, "UPDATE_TASK_NOTE", payload, mutate)


@api_endpoint("POST")
@api_authenticated
def sync_batch(request):
    payload = parse_json(request)
    data = process_sync_batch(
        request.user,
        payload.get("mutations"),
        request_context(request),
    )
    return success_response(request, data)


def _user_conflict(request, receipt_id):
    try:
        receipt = OfflineMutationReceipt.objects.select_related("task").get(
            pk=receipt_id,
            user=request.user,
        )
    except (OfflineMutationReceipt.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy xung đột ngoại tuyến.", status=404) from None
    if not receipt.conflict_payload:
        raise HousekeepingError("TASK_NOT_FOUND", "Bản ghi đồng bộ này không phải là một xung đột ngoại tuyến.", status=404)
    if receipt.task_id and not task_queryset_for_user(request.user).filter(pk=receipt.task_id).exists():
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy xung đột ngoại tuyến.", status=404)
    return receipt


@api_endpoint("GET")
@api_authenticated
def sync_conflict(request, receipt_id):
    return success_response(request, conflict_data(_user_conflict(request, receipt_id)))


@api_endpoint("POST")
@api_authenticated
def sync_conflict_resolve(request, receipt_id):
    payload = parse_json(request)
    receipt = _user_conflict(request, receipt_id)
    action = str(payload.get("action") or "").upper()
    if action not in {"DISCARD_LOCAL", "RETRY_WITH_SERVER_VERSION"}:
        raise APIError(
            "SYSTEM_ERROR",
            "Cách xử lý xung đột không hợp lệ.",
        )
    resolution_key = request.headers.get("Idempotency-Key")

    def mutate():
        if action == "DISCARD_LOCAL":
            resolved = discard_conflict(request.user, receipt_id)
            return conflict_data(resolved), None
        retry_key = str(payload.get("newIdempotencyKey") or "").strip()
        client_mutation_id = str(payload.get("clientMutationId") or retry_key).strip()
        if not retry_key or retry_key == str(resolution_key or "").strip():
            raise APIError(
                "IDEMPOTENCY_KEY_REQUIRED",
                "Retry cần newIdempotencyKey khác key của thao tác resolve.",
            )
        resolved, result = retry_conflict(
            request.user,
            receipt_id,
            idempotency_key=retry_key,
            client_mutation_id=client_mutation_id,
            context=request_context(request),
        )
        return {"conflict": conflict_data(resolved), "retry": result}, None

    data, replayed, _resolution_receipt = execute_idempotent(
        user=request.user,
        task=None,
        idempotency_key=resolution_key,
        operation=f"RESOLVE_OFFLINE_CONFLICT_{action}",
        payload=payload,
        base_version=None,
        mutation=mutate,
    )
    return success_response(request, data, replayed=replayed)


@api_endpoint("POST")
@api_authenticated
def sync_receipt_discard(request, receipt_id):
    payload = parse_json(request)
    try:
        receipt = OfflineMutationReceipt.objects.select_related("task").get(
            pk=receipt_id,
            user=request.user,
        )
    except (OfflineMutationReceipt.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy bản ghi đồng bộ cần bỏ.", status=404) from None
    if receipt.task_id and not task_queryset_for_user(request.user).filter(pk=receipt.task_id).exists():
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy bản ghi đồng bộ cần bỏ.", status=404)

    def mutate():
        discarded = discard_failed_receipt(request.user, receipt_id)
        return conflict_data(discarded), None

    data, replayed, _resolution_receipt = execute_idempotent(
        user=request.user,
        task=None,
        idempotency_key=request.headers.get("Idempotency-Key"),
        operation="DISCARD_OFFLINE_RECEIPT",
        payload=payload,
        base_version=None,
        mutation=mutate,
    )
    return success_response(request, data, replayed=replayed)


@api_endpoint("GET")
@api_authenticated
def completion_summary(request, task_id):
    task = task_for_detail(request.user, task_id)
    blockers = completion_blockers(task)
    pending_sync = next(
        (
            blocker["details"].get("pendingMutationCount", 0)
            + blocker["details"].get("pendingMediaCount", 0)
            for blocker in blockers
            if blocker["code"] == "PENDING_SYNC_EXISTS"
        ),
        0,
    )
    elapsed_seconds = None
    pause_seconds = 0
    excluded_pause_seconds = 0
    if task.started_at:
        end_time = task.completed_at or timezone.now()
        elapsed_seconds = max(
            0,
            int((end_time - task.started_at).total_seconds()),
        )
        for pause in task.pauses.all():
            duration = max(0, int(((pause.resumed_at or end_time) - pause.paused_at).total_seconds()))
            pause_seconds += duration
            if pause.excluded_from_sla:
                excluded_pause_seconds += duration
    return success_response(
        request,
        {
            "taskId": str(task.id),
            "version": task.version,
            "progressPercent": task.progress_percent,
            "elapsedSeconds": elapsed_seconds,
            "pauseSeconds": pause_seconds,
            "excludedPauseSeconds": excluded_pause_seconds,
            "activeDurationSeconds": max(0, elapsed_seconds - excluded_pause_seconds)
            if elapsed_seconds is not None
            else None,
            "checklistSummary": task_data(task, request.user)["checklistSummary"],
            "photoCount": task.photos.count(),
            "supplyRequestCount": task.supply_requests.count(),
            "issueCount": task.issues.count(),
            "pendingSyncCount": pending_sync,
            "canComplete": not blockers,
            "blockers": [
                {
                    "code": blocker["code"],
                    "message": blocker["message"],
                    **blocker["details"],
                }
                for blocker in blockers
            ],
        },
    )


@api_endpoint("POST")
@api_authenticated
def task_action(request, task_id, action):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        if action == "accept":
            task = accept_task(request.user, task_id, payload.get("version"), context)
        elif action == "start":
            verification = dict(payload.get("roomVerification") or {})
            for key in (
                "location",
                "wifiIdentifier",
                "cameraPhotoId",
                "guestConsentConfirmed",
                "guestConsentNote",
            ):
                if key in payload:
                    verification[key] = payload[key]
            task = start_task(
                request.user,
                task_id,
                payload.get("version"),
                context,
                verification,
            )
        elif action == "rework-start":
            verification = dict(payload.get("roomVerification") or {})
            for key in (
                "location",
                "wifiIdentifier",
                "cameraPhotoId",
                "guestConsentConfirmed",
                "guestConsentNote",
            ):
                if key in payload:
                    verification[key] = payload[key]
            task = start_task(
                request.user,
                task_id,
                payload.get("version"),
                context,
                verification,
            )
        elif action == "reject":
            task = reject_task(
                request.user,
                task_id,
                payload.get("version"),
                payload.get("reasonCode"),
                payload.get("note"),
                context,
            )
        elif action == "return":
            task = return_task(
                request.user,
                task_id,
                payload.get("version"),
                payload.get("reasonCode"),
                payload.get("note"),
                context,
            )
        elif action == "pause":
            task = pause_task(
                request.user,
                task_id,
                payload.get("version"),
                payload.get("reasonCode"),
                payload.get("note"),
                context,
            )
        elif action == "resume":
            task = resume_task(request.user, task_id, payload.get("version"), context)
        elif action == "complete":
            task = complete_task(
                request.user,
                task_id,
                payload.get("version"),
                payload.get("confirmFinalInspection") is True,
                payload.get("finalNote"),
                context,
            )
        elif action == "cancel":
            task = cancel_task(
                request.user,
                task_id,
                payload.get("version"),
                payload.get("reason"),
                context,
            )
        else:
            raise APIError("SYSTEM_ERROR", "Thao tác không hợp lệ.")
        return mutation_task_data(task), task.version

    return _run_task_mutation(request, task_id, action.upper().replace("-", "_"), payload, mutate)


@api_endpoint("PATCH")
@api_authenticated
def checklist_item(request, task_id, item_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        item, task = update_checklist_item(request.user, task_id, item_id, payload, context)
        return {
            "itemId": str(item.id),
            "status": item.status,
            "value": item.value,
            "progressPercent": task.progress_percent,
            "taskVersion": task.version,
            "itemVersion": item.update_version,
        }, task.version

    return _run_task_mutation(request, task_id, "UPDATE_CHECKLIST_ITEM", payload, mutate)


@api_endpoint("POST")
@api_authenticated
def checklist_failure_accept(request, task_id, item_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        item, task = accept_checklist_failure(
            request.user,
            task_id,
            item_id,
            payload.get("version"),
            payload.get("note"),
            context,
        )
        return {
            "itemId": str(item.id),
            "acceptedById": str(item.failure_accepted_by_id),
            "acceptedAt": item.failure_accepted_at.isoformat(),
            "itemVersion": item.update_version,
            "taskVersion": task.version,
        }, task.version

    return _run_task_mutation(request, task_id, "ACCEPT_CHECKLIST_FAILURE", payload, mutate)


@api_endpoint("POST")
@api_authenticated
def supply_request(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        supply, created = create_supply_request(request.user, task_id, payload, context)
        task = HousekeepingTask.objects.select_related("room").get(pk=task_id)
        return {
            "requestId": str(supply.id),
            "status": supply.status,
            "created": created,
            "taskStatus": task.status,
            "taskVersion": task.version,
        }, task.version

    return _run_task_mutation(request, task_id, "CREATE_SUPPLY_REQUEST", payload, mutate, status=201)


@api_endpoint("POST")
@api_authenticated
def issue(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        ticket, created = report_issue(request.user, task_id, payload, context)
        task = HousekeepingTask.objects.select_related("room").get(pk=task_id)
        return {
            "issueId": str(ticket.id),
            "status": ticket.status,
            "created": created,
            "taskStatus": task.status,
            "taskVersion": task.version,
        }, task.version

    return _run_task_mutation(request, task_id, "REPORT_ISSUE", payload, mutate, status=201)


@api_endpoint("POST")
@api_authenticated
def photo(request, task_id):
    image = request.FILES.get("image")
    if image is None:
        raise HousekeepingError("REQUIRED_PHOTO_MISSING", "Vui lòng chọn ảnh tải lên.")
    payload = {key: request.POST.get(key) for key in request.POST}
    if payload.get("metadata"):
        try:
            payload["metadata"] = json.loads(payload["metadata"])
        except json.JSONDecodeError:
            raise APIError(
                "SYSTEM_ERROR",
                "Thông tin bổ sung của ảnh không phải dữ liệu JSON hợp lệ.",
            ) from None
    digest = hashlib.sha256()
    for chunk in image.chunks():
        digest.update(chunk)
    image.seek(0)
    checksum = digest.hexdigest()
    if payload.get("checksum") and payload["checksum"] != checksum:
        raise APIError("SYSTEM_ERROR", "Checksum ảnh không khớp nội dung tải lên.")
    payload["checksum"] = checksum
    payload["fileName"] = image.name
    payload["fileSize"] = image.size
    context = request_context(request)

    def mutate():
        created_photo, task, created = upload_task_photo(request.user, task_id, image, payload, context)
        url = request.build_absolute_uri(created_photo.image.url)
        return {
            "photoId": str(created_photo.id),
            "url": url,
            "taskVersion": task.version,
            "created": created,
        }, task.version

    return _run_task_mutation(
        request,
        task_id,
        "UPLOAD_MEDIA",
        payload,
        mutate,
        status=201,
        client_mutation_id=payload.get("clientId", ""),
    )


@api_endpoint("POST")
@api_authenticated
def reassign(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        task = reassign_task(
            request.user,
            task_id,
            payload.get("assigneeId"),
            payload.get("version"),
            context,
            shift_id=payload.get("shiftId"),
            reason_code=payload.get("reasonCode", ""),
            note=payload.get("note", ""),
        )
        return mutation_task_data(task), task.version

    return _run_task_mutation(request, task_id, "REASSIGN_TASK", payload, mutate)


@api_endpoint("POST")
@api_authenticated
def handover(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        task = handover_task(
            request.user,
            task_id,
            payload.get("recipientId"),
            payload.get("version"),
            context,
            to_shift_id=payload.get("shiftId"),
            note=payload.get("note", ""),
            reconfirm_required_items=payload.get("reconfirmRequiredItems") or [],
        )
        return mutation_task_data(task), task.version

    return _run_task_mutation(request, task_id, "HANDOVER_TASK", payload, mutate)


@api_endpoint("PATCH")
@api_authenticated
def priority(request, task_id):
    payload = parse_json(request)
    context = request_context(request)

    def mutate():
        task = change_task_priority(
            request.user,
            task_id,
            payload.get("version"),
            payload.get("priority"),
            payload.get("reason"),
            context,
        )
        return mutation_task_data(task), task.version

    return _run_task_mutation(request, task_id, "CHANGE_TASK_PRIORITY", payload, mutate)


@api_endpoint("POST")
@api_authenticated
def qc_review(request, task_id, round_number=None):
    payload = parse_json(request)
    if payload.get("approved") is not True and "failedItems" not in payload:
        raise APIError(
            "TASK_INVALID_STATUS",
            "Khi kiểm tra chất lượng không đạt, phải gửi danh sách hạng mục không đạt; danh sách có thể rỗng nếu đánh giá tổng thể.",
        )
    context = request_context(request)

    def mutate():
        task, qc_task = review_qc(
            request.user,
            task_id,
            payload.get("version"),
            payload.get("approved") is True,
            payload.get("reason"),
            payload.get("note"),
            context,
            round_number=round_number,
            failed_items=payload.get("failedItems"),
            media_ids=payload.get("mediaIds"),
            deadline_at=payload.get("deadlineAt"),
        )
        result = mutation_task_data(task)
        result.update({"qcTaskId": str(qc_task.id), "qcRound": qc_task.round_number})
        return result, task.version

    operation = f"QC_REVIEW_ROUND_{round_number}" if round_number is not None else "QC_REVIEW"
    return _run_task_mutation(request, task_id, operation, payload, mutate)


def _support_filters(queryset, params, *, branch_path):
    statuses = [value for value in params.get("status", "").split(",") if value]
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    branch = params.get("branchId") or params.get("branch")
    if branch:
        try:
            branch_uuid = uuid.UUID(str(branch))
        except ValueError:
            queryset = queryset.filter(**{f"{branch_path}__code": branch})
        else:
            queryset = queryset.filter(**{f"{branch_path}__id": branch_uuid})
    if params.get("taskId"):
        queryset = queryset.filter(task_id=params["taskId"])
    return queryset


@api_endpoint("GET")
@api_authenticated
def supply_queue(request):
    queryset = _support_filters(
        scoped_supply_requests(request.user),
        request.GET,
        branch_path="branch",
    ).order_by("-created_at", "-id")
    page, limit = _pagination(request)
    total = queryset.count()
    offset = (page - 1) * limit
    rows = list(queryset[offset : offset + limit]) if offset < total else []
    total_pages = math.ceil(total / limit) if total else 0
    return success_response(
        request,
        [supply_request_data(row) for row in rows],
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1 and total > 0,
        },
    )


@api_endpoint("PATCH")
@api_authenticated
def supply_queue_update(request, request_id):
    payload = parse_json(request)
    try:
        supply = scoped_supply_requests(request.user).get(pk=request_id)
    except (SupplyRequest.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy yêu cầu vật tư.", status=404) from None
    context = request_context(request)

    def mutate():
        updated, task = update_supply_request_status(
            request.user,
            request_id,
            payload.get("version"),
            payload.get("status"),
            payload.get("note"),
            context,
        )
        return {
            "requestId": str(updated.id),
            "status": updated.status,
            "version": updated.version,
            "taskVersion": task.version,
        }, updated.version

    return _run_entity_mutation(request, supply.task, "UPDATE_SUPPLY_REQUEST", payload, mutate)


@api_endpoint("GET")
@api_authenticated
def issue_queue(request):
    queryset = _support_filters(
        scoped_issues(request.user),
        request.GET,
        branch_path="task__branch",
    ).order_by("-created_at", "-id")
    page, limit = _pagination(request)
    total = queryset.count()
    offset = (page - 1) * limit
    rows = list(queryset[offset : offset + limit]) if offset < total else []
    total_pages = math.ceil(total / limit) if total else 0
    return success_response(
        request,
        [issue_data(row) for row in rows],
        pagination={
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": total_pages,
            "hasNext": page < total_pages,
            "hasPrevious": page > 1 and total > 0,
        },
    )


@api_endpoint("PATCH")
@api_authenticated
def issue_queue_update(request, issue_id):
    payload = parse_json(request)
    try:
        issue = scoped_issues(request.user).get(pk=issue_id)
    except (IssueTicket.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy phiếu sự cố.", status=404) from None
    context = request_context(request)

    def mutate():
        updated, task = update_issue_status(
            request.user,
            issue_id,
            payload.get("version"),
            payload.get("status"),
            payload.get("note"),
            context,
            assigned_to_id=payload.get("assignedToId"),
        )
        return {
            "issueId": str(updated.id),
            "status": updated.status,
            "version": updated.version,
            "assignedToId": str(updated.assigned_to_id) if updated.assigned_to_id else None,
            "taskVersion": task.version,
        }, updated.version

    return _run_entity_mutation(request, issue.task, "UPDATE_ISSUE", payload, mutate)
