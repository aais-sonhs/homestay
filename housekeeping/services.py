import hashlib
import hmac
import math
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import User

from .checklist_validation import ChecklistValueError, validate_checklist_value
from .models import (
    Area,
    Booking,
    Branch,
    BranchHousekeepingPolicy,
    ChecklistVersion,
    HousekeepingActivityLog,
    HousekeepingTeam,
    HousekeepingTask,
    IssueTicket,
    OfflineMutationReceipt,
    QCFailedItem,
    QCTask,
    ReworkRound,
    Room,
    Shift,
    Skill,
    SupplyRequest,
    SupplyRequestItem,
    SupplyLocation,
    TaskAssignment,
    TaskChecklistItem,
    TaskHandover,
    TaskPause,
    TaskPhoto,
    TaskRoomVerification,
    TaskSLAState,
    TaskStatusHistory,
)
from .notifications import notify_task
from .permissions import (
    Capability,
    FIELD_ROLES,
    GLOBAL_ROLES,
    MANAGEMENT_ROLES,
    QC_ROLES,
    allowed_branch_ids as permission_branch_ids,
    decide_task_capability,
    membership_covers_task,
    membership_has_task_skills,
    membership_for,
)
from .selectors import prioritized_task_queryset
from .state_machine import Action, InvalidTaskTransition, apply_transition


class HousekeepingError(Exception):
    def __init__(self, code, message, *, status=400, details=None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        super().__init__(message)


PRIVILEGED_ROLES = GLOBAL_ROLES
HOUSEKEEPING_ROLES = FIELD_ROLES
ACTIVE_WORK_STATUSES = {
    HousekeepingTask.Status.ACCEPTED,
    HousekeepingTask.Status.IN_PROGRESS,
    HousekeepingTask.Status.PAUSED,
    HousekeepingTask.Status.WAITING_SUPPORT,
}
PAUSE_REASON_CODES = {
    "GUEST_IN_ROOM",
    "GUEST_REQUEST_LATER",
    "WAITING_SUPPLIES",
    "DEVICE_BROKEN",
    "WAITING_TECHNICIAN",
    "WAITING_MANAGER",
    "HIGHER_PRIORITY_TASK",
    "BREAK",
    "OTHER",
}
SUPPORT_PAUSE_REASONS = {
    "WAITING_SUPPLIES",
    "DEVICE_BROKEN",
    "WAITING_TECHNICIAN",
    "WAITING_MANAGER",
}


def request_context(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip()
    return {
        "ip": forwarded or request.META.get("REMOTE_ADDR") or None,
        "device_id": request.headers.get("X-Device-ID", "")[:255],
        "correlation_id": (
            getattr(request, "correlation_id", "")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )[:64],
        "idempotency_key": request.headers.get("Idempotency-Key", "")[:80],
    }


def allowed_branch_ids(user):
    return permission_branch_ids(user)


def _ensure_role(user, allowed_roles=HOUSEKEEPING_ROLES):
    if not user.is_active or user.is_deleted or user.role not in allowed_roles:
        raise HousekeepingError("TASK_ACCESS_DENIED", "Bạn không có quyền thực hiện thao tác này.", status=403)


def scoped_tasks(user):
    _ensure_role(user, HOUSEKEEPING_ROLES | {User.Role.QC})
    return prioritized_task_queryset(user)


def _get_task(user, task_id, *, lock=False, allowed_roles=HOUSEKEEPING_ROLES):
    _ensure_role(user, allowed_roles)
    queryset = HousekeepingTask.objects.select_related("branch", "room", "shift", "assignee")
    if lock:
        # Nullable ``select_related`` joins (shift/assignee) become LEFT JOINs.
        # PostgreSQL cannot lock the nullable side of an outer join, so make the
        # lock target explicit and keep the useful eager-loaded relationships.
        queryset = queryset.select_for_update(of=("self",))
    try:
        task = queryset.get(pk=task_id)
    except (HousekeepingTask.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy công việc.", status=404) from None
    branch_ids = allowed_branch_ids(user)
    if branch_ids is not None and task.branch_id not in branch_ids:
        raise HousekeepingError("USER_BRANCH_NOT_ALLOWED", "Bạn không có quyền tại chi nhánh này.", status=403)
    return task


def _require_capability(user, task, capability):
    decision = decide_task_capability(user, task, capability)
    if not decision.allowed:
        raise HousekeepingError(decision.code, decision.message, status=403)


def _check_version(task, version):
    try:
        requested_version = int(version)
    except (TypeError, ValueError):
        raise HousekeepingError("TASK_VERSION_CONFLICT", "Thiếu hoặc sai phiên bản công việc.", status=409) from None
    if task.version != requested_version:
        raise HousekeepingError(
            "TASK_VERSION_CONFLICT",
            "Công việc đã được người khác cập nhật. Vui lòng tải lại dữ liệu.",
            status=409,
            details={"currentVersion": task.version},
        )


def _log(task, user, action, context, *, from_status="", to_status="", changes=None):
    HousekeepingActivityLog.objects.create(
        task=task,
        user=user,
        branch=task.branch,
        action=action,
        from_status=from_status,
        to_status=to_status,
        ip_address=context.get("ip"),
        device_id=context.get("device_id", ""),
        correlation_id=context.get("correlation_id", ""),
        idempotency_key=context.get("idempotency_key", ""),
        changes=changes or {},
    )


def record_task_view(task, user, context):
    _log(
        task,
        user,
        "TASK_VIEWED",
        context,
        from_status=task.status,
        to_status=task.status,
        changes={"taskVersion": task.version},
    )


def _creation_datetime(value, label):
    parsed = parse_datetime(str(value or ""))
    if parsed is None:
        raise HousekeepingError("TASK_INVALID_STATUS", f"{label} không hợp lệ.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed)
    return parsed


def _creation_positive_int(value, label):
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HousekeepingError("TASK_INVALID_STATUS", f"{label} không hợp lệ.") from None
    if parsed < 1:
        raise HousekeepingError("TASK_INVALID_STATUS", f"{label} phải lớn hơn 0.")
    return parsed


@transaction.atomic
def create_task(user, payload, context):
    """Create a task and freeze its published checklist for manager workflows."""
    _ensure_role(user, MANAGEMENT_ROLES)
    try:
        branch = Branch.objects.select_for_update().get(
            pk=payload.get("branchId"),
            is_active=True,
        )
    except (Branch.DoesNotExist, ValueError, TypeError):
        raise HousekeepingError("USER_BRANCH_NOT_ALLOWED", "Chi nhánh không hợp lệ.", status=403) from None
    if user.role not in GLOBAL_ROLES:
        manager_membership = membership_for(user, branch.id)
        if not manager_membership or manager_membership.membership_role != "MANAGER":
            raise HousekeepingError("USER_BRANCH_NOT_ALLOWED", "Bạn không có quyền tạo công việc tại chi nhánh.", status=403)

    try:
        room = Room.objects.select_for_update().get(pk=payload.get("roomId"), branch=branch)
    except (Room.DoesNotExist, ValueError, TypeError):
        raise HousekeepingError("TASK_ACCESS_DENIED", "Phòng không thuộc chi nhánh đã chọn.", status=403) from None

    task_type = str(payload.get("taskType") or "")
    priority = str(payload.get("priority") or HousekeepingTask.Priority.NORMAL)
    if task_type not in HousekeepingTask.TaskType.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Loại công việc không hợp lệ.")
    if priority not in HousekeepingTask.Priority.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Mức ưu tiên không hợp lệ.")
    scheduled_start_at = _creation_datetime(payload.get("scheduledStartAt"), "Thời gian bắt đầu")
    due_at = _creation_datetime(payload.get("dueAt"), "Hạn hoàn thành")
    if due_at <= scheduled_start_at:
        raise HousekeepingError("TASK_INVALID_STATUS", "Hạn hoàn thành phải sau thời gian bắt đầu.")

    booking = None
    if payload.get("bookingId"):
        try:
            booking = Booking.objects.get(
                pk=payload.get("bookingId"),
                branch=branch,
                room=room,
            )
        except (Booking.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Đặt phòng không thuộc phòng đã chọn.", status=403) from None
    shift = None
    if payload.get("shiftId"):
        try:
            shift = Shift.objects.get(pk=payload.get("shiftId"), branch=branch, is_active=True)
        except (Shift.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Ca làm việc không hợp lệ.") from None
    area = room.area_ref
    if payload.get("areaId"):
        try:
            area = Area.objects.get(pk=payload.get("areaId"), branch=branch, is_active=True)
        except (Area.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Khu vực không hợp lệ.") from None
    team = None
    if payload.get("teamId"):
        try:
            team = HousekeepingTeam.objects.get(pk=payload.get("teamId"), branch=branch, is_active=True)
        except (HousekeepingTeam.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Nhóm Housekeeping không hợp lệ.") from None

    checklist_version = None
    if payload.get("checklistVersionId"):
        try:
            checklist_version = ChecklistVersion.objects.select_related("template").get(
                pk=payload.get("checklistVersionId"),
                status=ChecklistVersion.Status.PUBLISHED,
            )
        except (ChecklistVersion.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Danh sách kiểm tra chưa phát hành hoặc không tồn tại.") from None
        template = checklist_version.template
        if template.branch_id not in {None, branch.id} or (template.task_type and template.task_type != task_type):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Danh sách kiểm tra không áp dụng cho công việc này.")
    else:
        checklist_version = (
            ChecklistVersion.objects.select_related("template")
            .filter(
                status=ChecklistVersion.Status.PUBLISHED,
                template__is_active=True,
                template__task_type__in={"", task_type},
            )
            .filter(Q(template__branch=branch) | Q(template__branch__isnull=True))
            .order_by("-version_number", "id")
            .first()
        )
    if checklist_version is None:
        raise HousekeepingError("TASK_INVALID_STATUS", "Chưa có danh sách kiểm tra đã phát hành phù hợp.")

    skill_ids = payload.get("requiredSkillIds") or []
    if not isinstance(skill_ids, list):
        raise HousekeepingError("TASK_INVALID_STATUS", "Danh sách kỹ năng không hợp lệ.")
    required_skills = list(
        Skill.objects.filter(pk__in=skill_ids, is_active=True).filter(Q(branch=branch) | Q(branch__isnull=True))
    )
    if len(required_skills) != len(set(map(str, skill_ids))):
        raise HousekeepingError("TASK_ACCESS_DENIED", "Có kỹ năng không thuộc chi nhánh.")

    assignee = None
    if payload.get("assigneeId"):
        try:
            assignee = User.objects.get(
                pk=payload.get("assigneeId"),
                is_active=True,
                is_deleted=False,
            )
        except (User.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Nhân viên được giao không hợp lệ.") from None

    code = str(payload.get("code") or "").strip()[:30]
    if not code:
        code = f"HK-{timezone.localdate():%y%m%d}-{uuid.uuid4().hex[:8].upper()}"
    if HousekeepingTask.objects.filter(code=code).exists():
        raise HousekeepingError("TASK_INVALID_STATUS", "Mã công việc đã tồn tại.", status=409)
    status = HousekeepingTask.Status.PENDING_ACCEPTANCE if assignee else HousekeepingTask.Status.UNASSIGNED
    next_checkin_at = None
    if payload.get("nextCheckinAt"):
        next_checkin_at = _creation_datetime(payload.get("nextCheckinAt"), "Thời gian nhận phòng")
    standard_duration_minutes = _creation_positive_int(
        payload.get("standardDurationMinutes"),
        "Thời lượng chuẩn",
    )

    task = HousekeepingTask.objects.create(
        code=code,
        branch=branch,
        room=room,
        booking=booking,
        booking_code=booking.code if booking else str(payload.get("bookingCode") or "")[:50],
        task_type=task_type,
        priority=priority,
        status=status,
        assignee=assignee,
        assigned_by=user if assignee else None,
        shift=shift,
        team=team,
        area=area,
        checklist_version=checklist_version.version_label,
        checklist_template_version=checklist_version,
        scheduled_start_at=scheduled_start_at,
        due_at=due_at,
        next_checkin_at=next_checkin_at,
        standard_duration_minutes=standard_duration_minutes,
        requires_qc=payload.get("requiresQc") is not False,
        locked_by_manager=payload.get("lockedByManager") is True,
        guest_in_room=payload.get("guestInRoom") is True,
        special_request=str(payload.get("specialRequest") or ""),
        note=str(payload.get("note") or ""),
        created_by=user,
    )
    task.required_skills.set(required_skills)
    if assignee:
        assignee_membership = membership_for(assignee, branch.id)
        if (
            assignee_membership is None
            or not membership_covers_task(assignee_membership, task)
            or not membership_has_task_skills(assignee_membership, task)
        ):
            raise HousekeepingError("TASK_SKILL_NOT_ALLOWED", "Nhân viên không phù hợp phạm vi hoặc kỹ năng của công việc.", status=403)
        TaskAssignment.objects.create(
            task=task,
            assignee=assignee,
            assigned_by=user,
            shift=shift,
            team=team,
            status=TaskAssignment.Status.PENDING,
        )

    TaskChecklistItem.objects.bulk_create(
        [
            TaskChecklistItem(
                task=task,
                definition=definition,
                definition_key=definition.key,
                group_name=definition.group_name,
                title=definition.title,
                item_type=definition.item_type,
                is_required=definition.is_required,
                requires_photo=definition.required_photo_count > 0,
                options_snapshot=definition.options,
                validation_snapshot={
                    **definition.validation_rules,
                    "requiredPhotoCount": definition.required_photo_count,
                },
                sort_order=definition.sort_order,
            )
            for definition in checklist_version.item_definitions.all()
        ]
    )
    TaskStatusHistory.objects.create(
        task=task,
        from_status="",
        to_status=status,
        reason_code="TASK_CREATED",
        task_version=task.version,
        changed_by=user,
    )
    _log(
        task,
        user,
        "TASK_CREATED",
        context,
        to_status=status,
        changes={"source": str(payload.get("source") or "MANUAL"), "assigneeId": str(task.assignee_id or "")},
    )
    if room.status in {Room.Status.READY, Room.Status.DIRTY}:
        room.status = Room.Status.WAITING_CLEANING
        room.save(update_fields=["status"])
    from .sla import ensure_sla_state

    ensure_sla_state(task)
    if assignee:
        notify_task(
            task,
            "TASK_ASSIGNED",
            f"Bạn được giao công việc {task.code}",
            f"Phòng {room.code} đang chờ bạn nhận việc.",
            deduplication_key=f"task:{task.id}:created:assigned:{assignee.id}",
            users=[assignee],
            payload={"taskId": str(task.id), "taskVersion": task.version},
        )
    else:
        notify_task(
            task,
            "TASK_AVAILABLE",
            f"Có công việc mới tại phòng {room.code}",
            f"Công việc {task.code} đang chờ nhận.",
            deduplication_key=f"task:{task.id}:created:available",
            roles={"housekeeping", "housekeeping_lead"},
            payload={"taskId": str(task.id), "taskVersion": task.version},
        )
    return task


def _transition(
    task,
    user,
    to_status,
    event,
    context,
    *,
    transition_action,
    reason_code="",
    note="",
    changes=None,
    update_fields=None,
):
    try:
        result = apply_transition(
            task,
            action=transition_action,
            event=event,
            user=user,
            context=context,
            reason_code=reason_code,
            note=note,
            changes=changes,
            update_fields=update_fields,
        )
    except InvalidTaskTransition as error:
        raise HousekeepingError("TASK_INVALID_STATUS", str(error), status=409) from None
    if result.to_status != to_status:
        raise RuntimeError(
            f"State machine mismatch: {transition_action} expected {to_status}, got {result.to_status}."
        )


@transaction.atomic
def accept_task(user, task_id, version, context):
    task = _get_task(user, task_id, lock=True)
    if task.assignee_id and task.assignee_id != user.id:
        raise HousekeepingError("TASK_ALREADY_ASSIGNED", "Công việc đã được nhân viên khác nhận.", status=409)
    _require_capability(user, task, Capability.ACCEPT)
    _check_version(task, version)
    if task.status not in {HousekeepingTask.Status.UNASSIGNED, HousekeepingTask.Status.PENDING_ACCEPTANCE}:
        raise HousekeepingError("TASK_INVALID_STATUS", "Trạng thái công việc không cho phép nhận việc.", status=409)
    if task.locked_by_manager or task.status == HousekeepingTask.Status.CANCELLED:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc đang bị khóa hoặc đã hủy.", status=409)

    try:
        concurrent_limit = task.branch.housekeeping_policy.concurrent_task_limit
    except BranchHousekeepingPolicy.DoesNotExist:
        concurrent_limit = getattr(settings, "HOUSEKEEPING_CONCURRENT_TASK_LIMIT", 3)
    active_count = HousekeepingTask.objects.filter(assignee=user, status__in=ACTIVE_WORK_STATUSES).count()
    if active_count >= concurrent_limit:
        raise HousekeepingError("TASK_CONCURRENT_LIMIT_EXCEEDED", "Bạn đã đạt số công việc đồng thời tối đa.", status=409)

    task.assignee = user
    task.accepted_at = timezone.now()
    _transition(
        task,
        user,
        HousekeepingTask.Status.ACCEPTED,
        "TASK_ACCEPTED",
        context,
        transition_action=Action.ACCEPT,
        update_fields=["assignee", "accepted_at"],
    )
    assignment = task.assignments.select_for_update().filter(assignee=user, is_current=True).order_by("-assigned_at").first()
    if assignment is None:
        TaskAssignment.objects.create(
            task=task,
            assignee=user,
            assigned_by=task.assigned_by,
            shift=task.shift,
            team=task.team,
            status=TaskAssignment.Status.ACCEPTED,
            accepted_at=task.accepted_at,
        )
    else:
        assignment.status = TaskAssignment.Status.ACCEPTED
        assignment.accepted_at = task.accepted_at
        assignment.save(update_fields=["status", "accepted_at"])
    return task


@transaction.atomic
def start_task(user, task_id, version, context, room_verification=None):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.START)
    _check_version(task, version)
    if task.status not in {HousekeepingTask.Status.ACCEPTED, HousekeepingTask.Status.QC_REJECTED}:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc chưa sẵn sàng để bắt đầu.", status=409)
    task.room = Room.objects.select_for_update().get(pk=task.room_id)
    if task.room.status == Room.Status.OUT_OF_SERVICE or task.room.is_locked:
        raise HousekeepingError("ROOM_NOT_ACCESSIBLE", "Phòng đang ngừng phục vụ.", status=409)
    try:
        branch_policy = task.branch.housekeeping_policy
    except BranchHousekeepingPolicy.DoesNotExist:
        branch_policy = None
    allow_parallel = bool(branch_policy and branch_policy.allow_parallel_room_tasks)
    if not allow_parallel and HousekeepingTask.objects.filter(
        room_id=task.room_id,
        status__in={
            HousekeepingTask.Status.IN_PROGRESS,
            HousekeepingTask.Status.PAUSED,
            HousekeepingTask.Status.WAITING_SUPPORT,
        },
    ).exclude(pk=task.pk).exists():
        raise HousekeepingError(
            "ROOM_ALREADY_IN_PROGRESS",
            "Phòng đang được một nhân viên khác xử lý.",
            status=409,
        )

    _verify_room_access(task, user, room_verification or {}, context, branch_policy)

    is_rework = task.status == HousekeepingTask.Status.QC_REJECTED
    task.started_at = task.started_at or timezone.now()
    task.last_progress_at = timezone.now()
    task.updated_by = user
    fields = ["started_at", "last_progress_at", "updated_by"]
    action = "TASK_REWORK_STARTED" if is_rework else "TASK_STARTED"
    if is_rework:
        rework_round = (
            task.rework_rounds.select_for_update()
            .filter(status=ReworkRound.Status.PENDING)
            .order_by("-round_number")
            .first()
        )
        if rework_round is None:
            source_qc = task.qc_rounds.filter(status=QCTask.Status.REJECTED).order_by("-round_number").first()
            if source_qc is None:
                raise HousekeepingError("TASK_INVALID_STATUS", "Không tìm thấy lượt kiểm tra chất lượng yêu cầu làm lại.", status=409)
            rework_round = ReworkRound.objects.create(
                task=task,
                source_qc_round=source_qc,
                round_number=task.rework_rounds.count() + 1,
                failed_items_only=False,
                checklist_snapshot=source_qc.checklist_snapshot,
            )
        rework_started_at = timezone.now()
        rework_round.status = ReworkRound.Status.IN_PROGRESS
        rework_round.started_by = user
        rework_round.started_at = rework_started_at
        rework_round.save(update_fields=["status", "started_by", "started_at"])
        task.rework_count = max(task.rework_count + 1, rework_round.round_number)
        task.current_rework_round = rework_round.round_number
        task.rework_started_at = rework_started_at
        fields.extend(["rework_count", "current_rework_round", "rework_started_at"])
    _transition(
        task,
        user,
        HousekeepingTask.Status.IN_PROGRESS,
        action,
        context,
        transition_action=Action.START_REWORK if is_rework else Action.START,
        update_fields=fields,
    )
    return task


def _haversine_meters(latitude_a, longitude_a, latitude_b, longitude_b):
    earth_radius = 6_371_000
    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = math.radians(latitude_b - latitude_a)
    delta_lng = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lng / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    return earth_radius * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _verification_record(task, user, method, context, verification, **values):
    return TaskRoomVerification.objects.create(
        task=task,
        user=user,
        method=method,
        device_id=context.get("device_id", ""),
        guest_consent_confirmed=verification.get("guestConsentConfirmed") is True,
        guest_consent_note=str(verification.get("guestConsentNote") or ""),
        successful=True,
        **values,
    )


def _verify_room_access(task, user, verification, context, policy):
    method = str(verification.get("method") or "")
    method_value = str(verification.get("value") or "")
    created_count = 0

    qr_value = str(verification.get("qrCode") or (method_value if method == TaskRoomVerification.Method.QR_CODE else ""))
    qr_required = bool(policy and policy.require_qr_verification)
    if qr_required or qr_value:
        if not qr_value or not task.room.qr_identifier_hash:
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Công việc yêu cầu quét đúng mã QR của phòng.")
        submitted_hash = hashlib.sha256(qr_value.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(submitted_hash, task.room.qr_identifier_hash):
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Mã QR không thuộc phòng của công việc.")
        _verification_record(
            task,
            user,
            TaskRoomVerification.Method.QR_CODE,
            context,
            verification,
            submitted_value_hash=submitted_hash,
        )
        created_count += 1

    location = verification.get("location") or {}
    if method == TaskRoomVerification.Method.GPS:
        location = {
            "latitude": verification.get("latitude"),
            "longitude": verification.get("longitude"),
            "accuracyMeters": verification.get("accuracyMeters"),
        }
    gps_required = bool(policy and policy.require_gps_verification)
    if gps_required or location:
        if task.room.latitude is None or task.room.longitude is None:
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Phòng chưa được cấu hình tọa độ xác minh.")
        try:
            latitude = float(location.get("latitude"))
            longitude = float(location.get("longitude"))
            accuracy = float(location.get("accuracyMeters"))
        except (TypeError, ValueError):
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Dữ liệu GPS không hợp lệ.") from None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180) or accuracy < 0:
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Dữ liệu GPS ngoài phạm vi hợp lệ.")
        distance = _haversine_meters(
            latitude,
            longitude,
            float(task.room.latitude),
            float(task.room.longitude),
        )
        radius = task.room.verification_radius_meters
        if accuracy > radius or distance > radius:
            raise HousekeepingError(
                "ROOM_VERIFICATION_FAILED",
                "Vị trí hiện tại nằm ngoài phạm vi phòng.",
                details={"distanceMeters": round(distance, 1), "allowedRadiusMeters": radius},
            )
        _verification_record(
            task,
            user,
            TaskRoomVerification.Method.GPS,
            context,
            verification,
            latitude=latitude,
            longitude=longitude,
            accuracy_meters=accuracy,
            server_reference=f"distance_meters={distance:.1f}",
        )
        created_count += 1

    wifi_identifier = str(
        verification.get("wifiIdentifier")
        or (method_value if method == TaskRoomVerification.Method.WIFI else "")
    )
    wifi_required = bool(policy and policy.require_wifi_verification)
    if wifi_required or wifi_identifier:
        allowed_wifi = set(task.room.allowed_wifi_identifiers or [])
        if not wifi_identifier or wifi_identifier not in allowed_wifi:
            raise HousekeepingError("ROOM_VERIFICATION_FAILED", "Thiết bị chưa kết nối đúng Wi-Fi được phép.")
        _verification_record(
            task,
            user,
            TaskRoomVerification.Method.WIFI,
            context,
            verification,
            wifi_identifier=wifi_identifier[:255],
        )
        created_count += 1

    camera_photo_id = verification.get("cameraPhotoId") or (
        method_value if method == TaskRoomVerification.Method.CAMERA else ""
    )
    camera_required = bool(policy and policy.require_camera_verification)
    if camera_required or camera_photo_id:
        try:
            camera_photo = TaskPhoto.objects.get(
                pk=camera_photo_id,
                task=task,
                uploaded_by=user,
                category=TaskPhoto.Category.BEFORE,
                source__in={TaskPhoto.Source.CAMERA, TaskPhoto.Source.OFFLINE_CAMERA},
            )
        except (TaskPhoto.DoesNotExist, ValueError):
            raise HousekeepingError(
                "ROOM_VERIFICATION_FAILED",
                "Công việc yêu cầu ảnh chụp trực tiếp trước khi dọn.",
            ) from None
        _verification_record(
            task,
            user,
            TaskRoomVerification.Method.CAMERA,
            context,
            verification,
            server_reference=str(camera_photo.id),
        )
        created_count += 1

    guest_occupied = task.guest_in_room or task.room.is_guest_occupied
    if guest_occupied and (not policy or policy.require_guest_consent):
        if verification.get("guestConsentConfirmed") is not True:
            raise HousekeepingError("GUEST_CONSENT_REQUIRED", "Cần xác nhận khách đồng ý trước khi vào phòng.")
        if created_count == 0:
            _verification_record(
                task,
                user,
                TaskRoomVerification.Method.GUEST_CONSENT,
                context,
                verification,
            )


@transaction.atomic
def return_task(user, task_id, version, reason_code, note, context):
    if not str(reason_code or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Vui lòng chọn lý do trả công việc.")
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.RETURN)
    _check_version(task, version)
    before_start_statuses = {
        HousekeepingTask.Status.ASSIGNED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE,
        HousekeepingTask.Status.ACCEPTED,
    }
    after_start_statuses = {
        HousekeepingTask.Status.IN_PROGRESS,
        HousekeepingTask.Status.PAUSED,
        HousekeepingTask.Status.WAITING_SUPPORT,
    }
    try:
        allow_after_start = task.branch.housekeeping_policy.allow_return_after_start
    except BranchHousekeepingPolicy.DoesNotExist:
        allow_after_start = False
    if task.assignee_id != user.id or not (
        task.status in before_start_statuses
        or (allow_after_start and task.status in after_start_statuses)
    ):
        raise HousekeepingError("TASK_INVALID_STATUS", "Không thể trả lại công việc ở trạng thái hiện tại.", status=409)
    returned_after_start = task.status in after_start_statuses
    task.assignee = None
    task.accepted_at = None
    _transition(
        task,
        user,
        HousekeepingTask.Status.UNASSIGNED,
        "TASK_RETURNED",
        context,
        transition_action=Action.RETURN,
        reason_code=str(reason_code),
        note=str(note or ""),
        changes={"returnedAfterStart": returned_after_start, "progressPercent": task.progress_percent},
        update_fields=["assignee", "accepted_at"],
    )
    task.assignments.filter(is_current=True).update(
        status=TaskAssignment.Status.RETURNED,
        is_current=False,
        reason_code=str(reason_code),
        note=str(note or ""),
        ended_at=timezone.now(),
    )
    return task


def _recalculate_progress(task):
    required = task.checklist_items.filter(is_required=True)
    total = required.count()
    completed = required.filter(status=TaskChecklistItem.Status.COMPLETED).count()
    return round(completed * 100 / total) if total else 100


@transaction.atomic
def update_checklist_item(user, task_id, item_id, payload, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.UPDATE)
    _check_version(task, payload.get("version"))
    if task.assignee_id != user.id or task.status != HousekeepingTask.Status.IN_PROGRESS:
        raise HousekeepingError("TASK_INVALID_STATUS", "Chỉ người đang thực hiện mới được cập nhật danh sách kiểm tra.", status=409)
    try:
        item = TaskChecklistItem.objects.select_for_update().get(pk=item_id, task=task)
    except (TaskChecklistItem.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy hạng mục kiểm tra.", status=404) from None
    if task.current_rework_round:
        active_rework = task.rework_rounds.filter(
            round_number=task.current_rework_round,
            status=ReworkRound.Status.IN_PROGRESS,
            failed_items_only=True,
        ).first()
        if active_rework and not active_rework.source_qc_round.failed_items.filter(
            checklist_item=item,
            rework_required=True,
        ).exists():
            raise HousekeepingError(
                "TASK_ACCESS_DENIED",
                "Trong vòng làm lại này chỉ được sửa các hạng mục kiểm tra chất lượng không đạt.",
                status=403,
            )
    status = payload.get("status", TaskChecklistItem.Status.COMPLETED)
    if status not in TaskChecklistItem.Status.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Trạng thái hạng mục kiểm tra không hợp lệ.")
    if payload.get("itemVersion") is not None:
        try:
            item_version = int(payload.get("itemVersion"))
        except (TypeError, ValueError):
            raise HousekeepingError("TASK_VERSION_CONFLICT", "Phiên bản hạng mục kiểm tra không hợp lệ.", status=409) from None
        if item.update_version != item_version:
            raise HousekeepingError(
                "TASK_VERSION_CONFLICT",
                "Hạng mục kiểm tra đã được người khác cập nhật.",
                status=409,
                details={"currentItemVersion": item.update_version, "currentVersion": task.version},
            )
    try:
        normalized_value = validate_checklist_value(item, status, payload.get("value"))
    except ChecklistValueError as error:
        raise HousekeepingError(
            "INVALID_CHECKLIST_VALUE",
            str(error),
            details={"itemId": str(item.id), "itemType": item.item_type},
        ) from None
    failure_issue = None
    failure_reason = ""
    if status == TaskChecklistItem.Status.FAILED:
        failure_reason = str(payload.get("failureReason") or payload.get("note") or "").strip()
        failure_issue_id = payload.get("failureIssueId")
        if failure_issue_id:
            try:
                failure_issue = task.issues.get(pk=failure_issue_id)
            except (IssueTicket.DoesNotExist, ValueError):
                raise HousekeepingError("TASK_NOT_FOUND", "Phiếu xử lý hạng mục kiểm tra không hợp lệ.", status=404) from None
        if not failure_reason and failure_issue is None:
            raise HousekeepingError(
                "FAILED_ITEM_UNRESOLVED",
                "Hạng mục kiểm tra không đạt phải có lý do hoặc phiếu sự cố liên kết.",
            )
    item.status = status
    item.value = normalized_value
    item.note = str(payload.get("note") or "")
    item.failure_reason = failure_reason
    item.failure_issue = failure_issue
    # Any field update invalidates a previous managerial acceptance; the
    # exception decision must match the current reason/value.
    item.failure_accepted_by = None
    item.failure_accepted_at = None
    item.completed_by = user if status != TaskChecklistItem.Status.PENDING else None
    item.completed_at = timezone.now() if status != TaskChecklistItem.Status.PENDING else None
    item.update_version += 1
    item.save(
        update_fields=[
            "status",
            "value",
            "note",
            "failure_reason",
            "failure_issue",
            "failure_accepted_by",
            "failure_accepted_at",
            "completed_by",
            "completed_at",
            "update_version",
        ]
    )
    old_progress = task.progress_percent
    task.progress_percent = _recalculate_progress(task)
    task.last_progress_at = timezone.now()
    task.updated_by = user
    task.version += 1
    task.save(update_fields=["progress_percent", "last_progress_at", "updated_by", "version", "updated_at"])
    _log(task, user, "CHECKLIST_ITEM_UPDATED", context, changes={"itemId": str(item.id), "status": status, "progressPercent": task.progress_percent})
    if old_progress != task.progress_percent:
        _log(
            task,
            user,
            "TASK_PROGRESS_UPDATED",
            context,
            changes={"from": old_progress, "to": task.progress_percent},
        )
    return item, task


@transaction.atomic
def update_task_note(user, task_id, version, note, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.UPDATE)
    _check_version(task, version)
    manager_note = decide_task_capability(user, task, Capability.ASSIGN).allowed
    owner_note = task.assignee_id == user.id and task.status in ACTIVE_WORK_STATUSES
    if not manager_note and not owner_note:
        raise HousekeepingError(
            "TASK_INVALID_STATUS",
            "Chỉ người đang thực hiện hoặc người điều phối mới được cập nhật ghi chú công việc.",
            status=409,
        )
    if task.status in {HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED}:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc đã kết thúc, không thể thêm ghi chú.", status=409)
    previous_note = task.note
    task.note = str(note or "")
    task.last_progress_at = timezone.now()
    task.updated_by = user
    task.version += 1
    task.save(update_fields=["note", "last_progress_at", "updated_by", "version", "updated_at"])
    _log(
        task,
        user,
        "MANAGER_NOTE_ADDED" if manager_note and task.assignee_id != user.id else "TASK_NOTE_UPDATED",
        context,
        changes={"from": previous_note, "to": task.note},
    )
    if manager_note and task.assignee and task.assignee_id != user.id:
        notify_task(
            task,
            "MANAGER_NOTE_ADDED",
            f"Ghi chú mới cho công việc {task.code}",
            task.note or "Người điều phối đã cập nhật ghi chú công việc.",
            deduplication_key=f"task:{task.id}:manager-note:v{task.version}",
            users=[task.assignee],
            payload={"taskId": str(task.id), "taskVersion": task.version},
        )
    return task


@transaction.atomic
def accept_checklist_failure(user, task_id, item_id, version, note, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.ASSIGN)
    _check_version(task, version)
    try:
        item = TaskChecklistItem.objects.select_for_update().get(pk=item_id, task=task)
    except (TaskChecklistItem.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy hạng mục kiểm tra.", status=404) from None
    if item.status != TaskChecklistItem.Status.FAILED or not item.failure_reason:
        raise HousekeepingError(
            "FAILED_ITEM_UNRESOLVED",
            "Chỉ có thể chấp nhận mục Không đạt đã ghi lý do.",
            status=409,
        )
    item.failure_accepted_by = user
    item.failure_accepted_at = timezone.now()
    if note:
        item.note = str(note)
    item.update_version += 1
    item.save(
        update_fields=[
            "failure_accepted_by",
            "failure_accepted_at",
            "note",
            "update_version",
        ]
    )
    task.version += 1
    task.updated_by = user
    task.last_progress_at = timezone.now()
    task.save(update_fields=["version", "updated_by", "last_progress_at", "updated_at"])
    _log(
        task,
        user,
        "CHECKLIST_FAILURE_ACCEPTED",
        context,
        changes={"itemId": str(item.id), "itemVersion": item.update_version},
    )
    return item, task


@transaction.atomic
def upload_task_photo(user, task_id, image, payload, context):
    category = str(payload.get("category") or TaskPhoto.Category.AFTER)
    if category not in TaskPhoto.Category.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Loại ảnh không hợp lệ.")
    is_qc_media = category == TaskPhoto.Category.QC
    task = _get_task(
        user,
        task_id,
        lock=True,
        allowed_roles=QC_ROLES if is_qc_media else HOUSEKEEPING_ROLES,
    )
    _require_capability(user, task, Capability.QC_REVIEW if is_qc_media else Capability.UPDATE)
    if is_qc_media:
        if task.status != HousekeepingTask.Status.WAITING_QC:
            raise HousekeepingError("TASK_INVALID_STATUS", "Chỉ được tải ảnh kiểm tra chất lượng khi công việc đang chờ kiểm tra.", status=409)
    else:
        allowed_before_start = category == TaskPhoto.Category.BEFORE and task.status in {
            HousekeepingTask.Status.ACCEPTED,
            HousekeepingTask.Status.QC_REJECTED,
        }
        if task.assignee_id != user.id or not (
            task.status == HousekeepingTask.Status.IN_PROGRESS or allowed_before_start
        ):
            raise HousekeepingError("TASK_INVALID_STATUS", "Chỉ người thực hiện được tải ảnh ở bước phù hợp.", status=409)
    client_id = str(payload.get("clientId") or "")[:64]
    if client_id:
        existing = TaskPhoto.objects.filter(task=task, client_id=client_id).first()
        if existing:
            return existing, task, False
    _check_version(task, payload.get("version"))
    source = str(payload.get("source") or TaskPhoto.Source.CAMERA)
    if source not in TaskPhoto.Source.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Nguồn ảnh không hợp lệ.")
    checklist_item = None
    checklist_item_id = payload.get("checklistItemId")
    if checklist_item_id:
        try:
            checklist_item = task.checklist_items.get(pk=checklist_item_id)
        except (TaskChecklistItem.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy hạng mục kiểm tra.", status=404) from None
    try:
        policy = task.branch.housekeeping_policy
    except BranchHousekeepingPolicy.DoesNotExist:
        policy = None
    if (
        policy
        and policy.require_direct_camera_for_evidence
        and (category == TaskPhoto.Category.EVIDENCE or (checklist_item and checklist_item.requires_photo))
        and source == TaskPhoto.Source.GALLERY
    ):
        raise HousekeepingError("REQUIRED_PHOTO_MISSING", "Ảnh bằng chứng bắt buộc phải được chụp trực tiếp.")

    captured_at = timezone.now()
    if payload.get("capturedAt"):
        captured_at = parse_datetime(str(payload.get("capturedAt")))
        if captured_at is None:
            raise HousekeepingError("TASK_INVALID_STATUS", "Thời gian chụp ảnh không hợp lệ.")
        if timezone.is_naive(captured_at):
            captured_at = timezone.make_aware(captured_at)
    latitude = payload.get("latitude") or None
    longitude = payload.get("longitude") or None
    accuracy_meters = payload.get("accuracyMeters") or None
    try:
        if latitude is not None and not -90 <= float(latitude) <= 90:
            raise ValueError
        if longitude is not None and not -180 <= float(longitude) <= 180:
            raise ValueError
        if accuracy_meters is not None and float(accuracy_meters) < 0:
            raise ValueError
    except (TypeError, ValueError):
        raise HousekeepingError("TASK_INVALID_STATUS", "Tọa độ ảnh không hợp lệ.") from None

    issue = None
    if payload.get("issueId"):
        try:
            issue = task.issues.get(pk=payload.get("issueId"))
        except (IssueTicket.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_NOT_FOUND", "Phiếu sự cố gắn với ảnh không hợp lệ.", status=404) from None
    supply_request = None
    if payload.get("supplyRequestId"):
        try:
            supply_request = task.supply_requests.get(pk=payload.get("supplyRequestId"))
        except (SupplyRequest.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_NOT_FOUND", "Yêu cầu vật tư gắn với ảnh không hợp lệ.", status=404) from None
    qc_round = None
    if is_qc_media:
        qc_round_id = payload.get("qcRoundId")
        qc_queryset = task.qc_rounds.filter(status=QCTask.Status.PENDING)
        if qc_round_id:
            qc_queryset = qc_queryset.filter(pk=qc_round_id)
        qc_round = qc_queryset.order_by("-round_number").first()
        if qc_round is None:
            raise HousekeepingError("TASK_INVALID_STATUS", "Không tìm thấy lượt kiểm tra chất lượng đang chờ.", status=409)
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise HousekeepingError("TASK_INVALID_STATUS", "Thông tin bổ sung của ảnh phải là một đối tượng dữ liệu.")
    photo = TaskPhoto.objects.create(
        task=task,
        checklist_item=checklist_item,
        issue=issue,
        supply_request=supply_request,
        qc_round=qc_round,
        room=task.room,
        uploaded_by=user,
        category=category,
        image=image,
        source=source,
        client_id=client_id,
        checksum=str(payload.get("checksum") or "")[:64],
        captured_at=captured_at,
        latitude=latitude,
        longitude=longitude,
        accuracy_meters=accuracy_meters,
        device_id=context.get("device_id", ""),
        metadata=metadata,
    )
    task.version += 1
    task.last_progress_at = timezone.now()
    task.updated_by = user
    task.save(update_fields=["version", "last_progress_at", "updated_by", "updated_at"])
    _log(
        task,
        user,
        "PHOTO_ADDED",
        context,
        changes={"photoId": str(photo.id), "category": category},
    )
    return photo, task, True


@transaction.atomic
def pause_task(user, task_id, version, reason_code, note, context):
    reason_code = str(reason_code or "")
    if reason_code not in PAUSE_REASON_CODES:
        raise HousekeepingError("TASK_INVALID_STATUS", "Vui lòng chọn lý do tạm dừng.")
    if reason_code == "OTHER" and not str(note or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Lý do khác phải có ghi chú.")
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.PAUSE)
    _check_version(task, version)
    if task.assignee_id != user.id or task.status != HousekeepingTask.Status.IN_PROGRESS:
        raise HousekeepingError("TASK_INVALID_STATUS", "Không thể tạm dừng công việc.", status=409)
    TaskPause.objects.create(
        task=task,
        previous_status=task.status,
        reason_code=reason_code,
        note=note or "",
        excluded_from_sla=reason_code in SUPPORT_PAUSE_REASONS,
        paused_by=user,
    )
    task.pause_reason = reason_code
    task.last_progress_at = timezone.now()
    task.updated_by = user
    status = (
        HousekeepingTask.Status.WAITING_SUPPORT
        if reason_code in SUPPORT_PAUSE_REASONS
        else HousekeepingTask.Status.PAUSED
    )
    _transition(
        task,
        user,
        status,
        "TASK_PAUSED",
        context,
        transition_action=Action.WAIT_SUPPORT if status == HousekeepingTask.Status.WAITING_SUPPORT else Action.PAUSE,
        reason_code=reason_code,
        note=note or "",
        update_fields=["pause_reason", "last_progress_at", "updated_by"],
    )
    return task


@transaction.atomic
def resume_task(user, task_id, version, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.RESUME)
    _check_version(task, version)
    if task.assignee_id != user.id or task.status not in {HousekeepingTask.Status.PAUSED, HousekeepingTask.Status.WAITING_SUPPORT}:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc không ở trạng thái có thể tiếp tục.", status=409)
    if task.issues.exclude(status__in={IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED}).filter(
        blocks_room_ready=True
    ).exists():
        raise HousekeepingError("BLOCKING_ISSUE_EXISTS", "Sự cố chặn phòng chưa được xử lý.", status=409)
    pause = task.pauses.select_for_update().filter(resumed_at__isnull=True).order_by("-paused_at").first()
    pause_duration_seconds = 0
    if pause:
        resumed_at = timezone.now()
        pause.resumed_by = user
        pause.resumed_at = resumed_at
        pause.save(update_fields=["resumed_by", "resumed_at"])
        pause_duration_seconds = max(0, int((resumed_at - pause.paused_at).total_seconds()))
        if pause.excluded_from_sla and pause_duration_seconds:
            TaskSLAState.objects.select_for_update().filter(task=task).update(
                excluded_pause_seconds=F("excluded_pause_seconds") + pause_duration_seconds
            )
    task.pause_reason = ""
    task.last_progress_at = timezone.now()
    task.updated_by = user
    _transition(
        task,
        user,
        HousekeepingTask.Status.IN_PROGRESS,
        "TASK_RESUMED",
        context,
        transition_action=Action.RESUME,
        changes={
            "pauseDurationSeconds": pause_duration_seconds,
            "excludedFromSLA": bool(pause and pause.excluded_from_sla),
        },
        update_fields=["pause_reason", "last_progress_at", "updated_by"],
    )
    return task


@transaction.atomic
def create_supply_request(user, task_id, payload, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.UPDATE)
    if task.assignee_id != user.id or task.status not in ACTIVE_WORK_STATUSES:
        raise HousekeepingError("TASK_ACCESS_DENIED", "Bạn không phải người thực hiện công việc.", status=403)
    items = payload.get("items") or []
    if not items:
        raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Vui lòng nhập vật tư cần cấp.")
    client_id = str(payload.get("clientRequestId") or "")[:64]
    if client_id:
        existing = SupplyRequest.objects.filter(task=task, requested_by=user, client_request_id=client_id).first()
        if existing:
            return existing, False
    if "version" in payload:
        _check_version(task, payload.get("version"))
    priority = payload.get("priority", HousekeepingTask.Priority.NORMAL)
    if priority not in HousekeepingTask.Priority.values:
        raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Mức ưu tiên vật tư không hợp lệ.")
    destination = None
    destination_id = payload.get("destinationId")
    if destination_id:
        try:
            destination = SupplyLocation.objects.get(pk=destination_id, branch=task.branch, is_active=True)
        except (SupplyLocation.DoesNotExist, ValueError):
            raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Điểm cấp vật tư không hợp lệ.") from None
    else:
        destination = SupplyLocation.objects.filter(branch=task.branch, is_active=True).order_by("name", "id").first()
    supply = SupplyRequest.objects.create(
        task=task,
        branch=task.branch,
        requested_by=user,
        destination=destination,
        priority=priority,
        note=str(payload.get("note") or ""),
        warehouse=str(payload.get("warehouse") or ""),
        blocks_completion=payload.get("blocksCompletion") is not False,
        client_request_id=client_id,
    )
    for item in items:
        inventory_item_id = str(item.get("inventoryItemId") or "").strip()
        item_name = str(item.get("name") or "").strip()
        if not inventory_item_id and not item_name:
            raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Vật tư phải có mã hoặc tên.")
        try:
            quantity = Decimal(str(item.get("quantity", 0)))
        except InvalidOperation:
            raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Số lượng vật tư không hợp lệ.") from None
        if quantity <= 0:
            raise HousekeepingError("SUPPLY_REQUEST_PENDING", "Số lượng vật tư phải lớn hơn 0.")
        SupplyRequestItem.objects.create(
            request=supply,
            inventory_item_id=inventory_item_id,
            item_name=item_name,
            quantity=quantity,
            unit=str(item.get("unit") or "Cái"),
        )
    attachment_ids = payload.get("attachmentIds") or []
    if not isinstance(attachment_ids, list):
        raise HousekeepingError("TASK_INVALID_STATUS", "Danh sách ảnh vật tư không hợp lệ.")
    if attachment_ids:
        try:
            normalized_attachment_ids = {uuid.UUID(str(photo_id)) for photo_id in attachment_ids}
        except ValueError:
            raise HousekeepingError("TASK_NOT_FOUND", "ID ảnh vật tư không hợp lệ.", status=404) from None
        photos = list(
            task.photos.select_for_update().filter(pk__in=normalized_attachment_ids, uploaded_by=user)
        )
        if len(photos) != len(normalized_attachment_ids):
            raise HousekeepingError("TASK_NOT_FOUND", "Có ảnh vật tư không thuộc công việc.", status=404)
        TaskPhoto.objects.filter(pk__in=[photo.pk for photo in photos]).update(
            supply_request=supply,
            category=TaskPhoto.Category.SUPPLY,
        )
    if task.status == HousekeepingTask.Status.IN_PROGRESS:
        task.pause_reason = "WAITING_SUPPLIES"
        task.last_progress_at = timezone.now()
        task.updated_by = user
        TaskPause.objects.create(
            task=task,
            previous_status=HousekeepingTask.Status.IN_PROGRESS,
            reason_code="WAITING_SUPPLIES",
            note=str(payload.get("note") or ""),
            excluded_from_sla=True,
            paused_by=user,
        )
        _transition(
            task,
            user,
            HousekeepingTask.Status.WAITING_SUPPORT,
            "SUPPLY_REQUEST_CREATED",
            context,
            transition_action=Action.WAIT_SUPPORT,
            reason_code="WAITING_SUPPLIES",
            update_fields=["pause_reason", "last_progress_at", "updated_by"],
        )
    else:
        task.version += 1
        task.updated_by = user
        task.last_progress_at = timezone.now()
        task.save(update_fields=["version", "updated_by", "last_progress_at", "updated_at"])
        _log(task, user, "SUPPLY_REQUEST_CREATED", context, changes={"requestId": str(supply.id)})
    notify_task(
        task,
        "SUPPLY_REQUEST_CREATED",
        f"Yêu cầu vật tư cho phòng {task.room.code}",
        f"Công việc {task.code} đang chờ cấp vật tư.",
        deduplication_key=f"supply:{supply.id}:created",
        roles={"warehouse"},
        payload={"taskId": str(task.id), "supplyRequestId": str(supply.id)},
    )
    return supply, True


@transaction.atomic
def report_issue(user, task_id, payload, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.UPDATE)
    if task.assignee_id != user.id or task.status not in ACTIVE_WORK_STATUSES:
        raise HousekeepingError("TASK_ACCESS_DENIED", "Bạn không phải người thực hiện công việc.", status=403)
    description = str(payload.get("description") or "").strip()
    if not description:
        raise HousekeepingError("TASK_INVALID_STATUS", "Vui lòng mô tả sự cố.")
    client_id = str(payload.get("clientRequestId") or "")[:64]
    if client_id:
        existing = IssueTicket.objects.filter(task=task, reported_by=user, client_request_id=client_id).first()
        if existing:
            return existing, False
    if "version" in payload:
        _check_version(task, payload.get("version"))
    room_id = payload.get("roomId")
    if room_id and str(room_id) != str(task.room_id):
        raise HousekeepingError("TASK_ACCESS_DENIED", "Phòng xảy ra sự cố không khớp với công việc.", status=403)
    severity = payload.get("severity", HousekeepingTask.Priority.NORMAL)
    if severity not in HousekeepingTask.Priority.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Mức độ sự cố không hợp lệ.")
    issue = IssueTicket.objects.create(
        task=task,
        room=task.room,
        booking=task.booking,
        reported_by=user,
        device_id=str(payload.get("deviceId") or ""),
        issue_type=str(payload.get("issueType") or "OTHER"),
        severity=severity,
        description=description,
        blocks_room_ready=bool(payload.get("blocksRoomReady")),
        client_request_id=client_id,
    )
    attachment_ids = payload.get("attachmentIds") or []
    if not isinstance(attachment_ids, list):
        raise HousekeepingError("TASK_INVALID_STATUS", "Danh sách ảnh sự cố không hợp lệ.")
    if attachment_ids:
        try:
            normalized_attachment_ids = {uuid.UUID(str(photo_id)) for photo_id in attachment_ids}
        except ValueError:
            raise HousekeepingError("TASK_NOT_FOUND", "ID ảnh sự cố không hợp lệ.", status=404) from None
        photos = list(
            task.photos.select_for_update().filter(pk__in=normalized_attachment_ids, uploaded_by=user)
        )
        if len(photos) != len(normalized_attachment_ids):
            raise HousekeepingError("TASK_NOT_FOUND", "Có ảnh sự cố không thuộc công việc.", status=404)
        TaskPhoto.objects.filter(pk__in=[photo.pk for photo in photos]).update(
            issue=issue,
            category=TaskPhoto.Category.ISSUE,
        )
    if issue.blocks_room_ready and task.status == HousekeepingTask.Status.IN_PROGRESS:
        task.pause_reason = "DEVICE_BROKEN"
        task.last_progress_at = timezone.now()
        task.updated_by = user
        TaskPause.objects.create(
            task=task,
            previous_status=HousekeepingTask.Status.IN_PROGRESS,
            reason_code="DEVICE_BROKEN",
            note=description,
            excluded_from_sla=True,
            paused_by=user,
        )
        _transition(
            task,
            user,
            HousekeepingTask.Status.WAITING_SUPPORT,
            "ISSUE_REPORTED",
            context,
            transition_action=Action.WAIT_SUPPORT,
            reason_code="DEVICE_BROKEN",
            update_fields=["pause_reason", "last_progress_at", "updated_by"],
        )
    else:
        task.version += 1
        task.updated_by = user
        task.last_progress_at = timezone.now()
        task.save(update_fields=["version", "updated_by", "last_progress_at", "updated_at"])
        _log(task, user, "ISSUE_REPORTED", context, changes={"issueId": str(issue.id), "blocksRoomReady": issue.blocks_room_ready})
    notify_task(
        task,
        "ISSUE_REPORTED",
        f"Sự cố tại phòng {task.room.code}",
        description,
        deduplication_key=f"issue:{issue.id}:created",
        roles={"technician"},
        payload={"taskId": str(task.id), "issueId": str(issue.id), "severity": issue.severity},
    )
    return issue, True


def completion_blockers(task, *, exclude_idempotency_key=""):
    blockers = []
    incomplete = list(
        task.checklist_items.filter(
            is_required=True,
            status=TaskChecklistItem.Status.PENDING,
        ).values("id", "title")
    )
    if incomplete:
        blockers.append(
            {
                "code": "CHECKLIST_REQUIRED_INCOMPLETE",
                "message": "Còn hạng mục kiểm tra bắt buộc chưa hoàn tất.",
                "status": 400,
                "details": {
                    "items": [{"id": str(item["id"]), "title": item["title"]} for item in incomplete]
                },
            }
        )

    unresolved_failed = list(
        task.checklist_items.filter(
            is_required=True,
            status=TaskChecklistItem.Status.FAILED,
            failure_issue__isnull=True,
            failure_accepted_by__isnull=True,
        ).values("id", "title")
    )
    if unresolved_failed:
        blockers.append(
            {
                "code": "FAILED_ITEM_UNRESOLVED",
                "message": "Hạng mục kiểm tra không đạt phải có phiếu sự cố hoặc lý do được chấp nhận.",
                "status": 400,
                "details": {
                    "items": [
                        {"id": str(item["id"]), "title": item["title"]}
                        for item in unresolved_failed
                    ]
                },
            }
        )

    missing_photos = []
    photo_items = task.checklist_items.filter(is_required=True).filter(
        Q(requires_photo=True) | Q(item_type=TaskChecklistItem.ItemType.PHOTO)
    )
    for item in photo_items:
        required_count = max(1, int((item.validation_snapshot or {}).get("requiredPhotoCount", 1)))
        synced_count = item.photos.filter(sync_status=TaskPhoto.SyncStatus.SYNCED).count()
        if synced_count < required_count:
            missing_photos.append(
                {
                    "id": str(item.id),
                    "title": item.title,
                    "requiredCount": required_count,
                    "syncedCount": synced_count,
                }
            )
    if missing_photos:
        blockers.append(
            {
                "code": "REQUIRED_PHOTO_MISSING",
                "message": "Thiếu ảnh bắt buộc đã đồng bộ.",
                "status": 400,
                "details": {"items": missing_photos},
            }
        )

    if task.issues.exclude(
        status__in={IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED}
    ).filter(blocks_room_ready=True).exists():
        blockers.append(
            {
                "code": "BLOCKING_ISSUE_EXISTS",
                "message": "Còn sự cố chặn phòng chưa xử lý.",
                "status": 409,
                "details": {},
            }
        )

    try:
        policy = task.branch.housekeeping_policy
    except BranchHousekeepingPolicy.DoesNotExist:
        policy = None
    if (not policy or policy.block_completion_with_pending_supply) and task.supply_requests.filter(
        blocks_completion=True,
        status__in={SupplyRequest.Status.PENDING, SupplyRequest.Status.ACKNOWLEDGED},
    ).exists():
        blockers.append(
            {
                "code": "SUPPLY_REQUEST_PENDING",
                "message": "Còn yêu cầu vật tư chặn hoàn thành.",
                "status": 409,
                "details": {},
            }
        )

    if not policy or policy.block_completion_with_pending_sync:
        pending_receipts = task.offline_receipts.filter(
            status__in={
                OfflineMutationReceipt.Status.RECEIVED,
                OfflineMutationReceipt.Status.FAILED,
                OfflineMutationReceipt.Status.CONFLICT,
            }
        )
        if exclude_idempotency_key:
            pending_receipts = pending_receipts.exclude(idempotency_key=exclude_idempotency_key)
        pending_media = task.photos.exclude(sync_status=TaskPhoto.SyncStatus.SYNCED).count()
        pending_mutations = pending_receipts.count()
        if pending_mutations or pending_media:
            blockers.append(
                {
                    "code": "PENDING_SYNC_EXISTS",
                    "message": "Còn dữ liệu ngoại tuyến hoặc ảnh chưa đồng bộ.",
                    "status": 409,
                    "details": {
                        "pendingMutationCount": pending_mutations,
                        "pendingMediaCount": pending_media,
                    },
                }
            )
    return blockers


@transaction.atomic
def complete_task(user, task_id, version, confirm_final_inspection, final_note, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.COMPLETE)
    _check_version(task, version)
    if task.assignee_id != user.id or task.status != HousekeepingTask.Status.IN_PROGRESS:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc chưa thể hoàn thành.", status=409)
    if not confirm_final_inspection:
        raise HousekeepingError("CHECKLIST_REQUIRED_INCOMPLETE", "Vui lòng xác nhận kiểm tra cuối phòng.")
    blockers = completion_blockers(
        task,
        exclude_idempotency_key=context.get("idempotency_key", ""),
    )
    if blockers:
        blocker = blockers[0]
        raise HousekeepingError(
            blocker["code"],
            blocker["message"],
            status=blocker["status"],
            details=blocker["details"],
        )

    task.completed_at = timezone.now()
    task.note = final_note or task.note
    task.last_progress_at = timezone.now()
    task.updated_by = user
    fields = ["completed_at", "note", "last_progress_at", "updated_by"]
    _transition(
        task,
        user,
        HousekeepingTask.Status.COMPLETED,
        "TASK_COMPLETED",
        context,
        transition_action=Action.COMPLETE,
        update_fields=fields,
    )
    if task.requires_qc:
        checklist_snapshot = list(
            task.checklist_items.order_by("sort_order", "id").values(
                "id",
                "definition_key",
                "group_name",
                "title",
                "item_type",
                "is_required",
                "status",
                "value",
                "note",
                "options_snapshot",
                "validation_snapshot",
                "failure_reason",
                "failure_issue_id",
                "failure_accepted_by_id",
                "failure_accepted_at",
                "completed_by_id",
                "completed_at",
            )
        )
        for snapshot in checklist_snapshot:
            snapshot["id"] = str(snapshot["id"])
            for key in ("failure_issue_id", "failure_accepted_by_id", "completed_by_id"):
                snapshot[key] = str(snapshot[key]) if snapshot[key] else None
            for key in ("failure_accepted_at", "completed_at"):
                snapshot[key] = snapshot[key].isoformat() if snapshot[key] else None
        qc_task = QCTask.objects.create(
            task=task,
            round_number=task.qc_rounds.count() + 1,
            checklist_snapshot=checklist_snapshot,
        )
        active_rework = task.rework_rounds.select_for_update().filter(
            round_number=task.current_rework_round,
            status=ReworkRound.Status.IN_PROGRESS,
        ).first()
        if active_rework:
            active_rework.status = ReworkRound.Status.SENT_TO_QC
            active_rework.completed_at = task.completed_at
            active_rework.sent_to_qc_at = timezone.now()
            active_rework.save(
                update_fields=["status", "completed_at", "sent_to_qc_at"]
            )
        transition_action = Action.SEND_TO_QC
        to_status = HousekeepingTask.Status.WAITING_QC
        event = "TASK_SENT_TO_QC"
    else:
        transition_action = Action.COMPLETE_WITHOUT_QC
        to_status = HousekeepingTask.Status.QC_APPROVED
        event = "TASK_QC_APPROVED"
    _transition(
        task,
        user,
        to_status,
        event,
        context,
        transition_action=transition_action,
    )
    if task.requires_qc:
        notify_task(
            task,
            "TASK_READY_FOR_QC",
            f"Phòng {task.room.code} sẵn sàng kiểm tra chất lượng",
            f"Công việc {task.code} đã hoàn thành và đang chờ kiểm tra vòng {qc_task.round_number}.",
            deduplication_key=f"task:{task.id}:qc:{qc_task.round_number}:ready",
            roles={"qc"},
            payload={
                "taskId": str(task.id),
                "qcTaskId": str(qc_task.id),
                "qcRound": qc_task.round_number,
                "priority": task.priority,
                "nextCheckinAt": task.next_checkin_at.isoformat() if task.next_checkin_at else None,
            },
        )
    return task


@transaction.atomic
def review_qc(
    user,
    task_id,
    version,
    approved,
    reason,
    note,
    context,
    *,
    round_number=None,
    failed_items=None,
    media_ids=None,
    deadline_at=None,
):
    task = _get_task(user, task_id, lock=True, allowed_roles=QC_ROLES)
    _require_capability(user, task, Capability.QC_REVIEW)
    _check_version(task, version)
    if task.status != HousekeepingTask.Status.WAITING_QC:
        raise HousekeepingError("TASK_INVALID_STATUS", "Công việc không ở trạng thái chờ kiểm tra chất lượng.", status=409)
    qc_queryset = task.qc_rounds.select_for_update().filter(status=QCTask.Status.PENDING)
    if round_number is not None:
        qc_queryset = qc_queryset.filter(round_number=round_number)
    qc_task = qc_queryset.order_by("-round_number").first()
    if qc_task is None:
        raise HousekeepingError("TASK_INVALID_STATUS", "Không tìm thấy lượt kiểm tra chất lượng đang chờ.", status=409)
    if not approved and not str(reason or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Kiểm tra chất lượng không đạt phải có lý do.")
    failed_items = failed_items if failed_items is not None else []
    media_ids = media_ids or []
    if not isinstance(failed_items, list) or not isinstance(media_ids, list):
        raise HousekeepingError("TASK_INVALID_STATUS", "Danh sách kiểm tra chất lượng không hợp lệ.")
    normalized_failed_items = []
    seen_item_ids = set()
    if not approved:
        for entry in failed_items:
            if not isinstance(entry, dict):
                raise HousekeepingError("TASK_INVALID_STATUS", "Hạng mục kiểm tra chất lượng không hợp lệ.")
            try:
                checklist_item = task.checklist_items.get(pk=entry.get("checklistItemId"))
            except (TaskChecklistItem.DoesNotExist, ValueError):
                raise HousekeepingError("TASK_NOT_FOUND", "Hạng mục kiểm tra chất lượng không thuộc công việc.", status=404) from None
            if checklist_item.id in seen_item_ids:
                raise HousekeepingError("TASK_INVALID_STATUS", "Hạng mục kiểm tra chất lượng bị lặp.")
            item_reason = str(entry.get("reason") or "").strip()
            if not item_reason:
                raise HousekeepingError("TASK_INVALID_STATUS", "Hạng mục kiểm tra chất lượng không đạt phải có lý do.")
            seen_item_ids.add(checklist_item.id)
            normalized_failed_items.append(
                {
                    "item": checklist_item,
                    "checklistItemId": str(checklist_item.id),
                    "title": checklist_item.title,
                    "reasonCode": str(entry.get("reasonCode") or ""),
                    "reason": item_reason,
                    "note": str(entry.get("note") or ""),
                    "reworkRequired": entry.get("reworkRequired") is not False,
                }
            )

    try:
        normalized_media_ids = {uuid.UUID(str(media_id)) for media_id in media_ids}
    except ValueError:
        raise HousekeepingError("TASK_NOT_FOUND", "Mã ảnh kiểm tra chất lượng không hợp lệ.", status=404) from None
    qc_media = list(
        task.photos.select_for_update().filter(
            pk__in=normalized_media_ids,
            category=TaskPhoto.Category.QC,
            uploaded_by=user,
        )
    )
    if len(qc_media) != len(normalized_media_ids):
        raise HousekeepingError("TASK_NOT_FOUND", "Có ảnh không thuộc lượt kiểm tra chất lượng.", status=404)

    reviewed_at = timezone.now()
    parsed_deadline = None
    if not approved:
        if deadline_at:
            parsed_deadline = parse_datetime(str(deadline_at))
            if parsed_deadline is None:
                raise HousekeepingError("TASK_INVALID_STATUS", "Thời hạn làm lại không hợp lệ.")
            if timezone.is_naive(parsed_deadline):
                parsed_deadline = timezone.make_aware(parsed_deadline)
        else:
            parsed_deadline = task.next_checkin_at or reviewed_at + timedelta(minutes=30)
        if parsed_deadline <= reviewed_at:
            raise HousekeepingError("TASK_INVALID_STATUS", "Thời hạn làm lại phải ở tương lai.")

    qc_task.status = QCTask.Status.APPROVED if approved else QCTask.Status.REJECTED
    qc_task.reviewer = user
    qc_task.reason = str(reason or "")
    qc_task.note = str(note or "")
    qc_task.reviewed_at = reviewed_at
    qc_task.deadline_at = parsed_deadline
    qc_task.result_snapshot = {
        "approved": bool(approved),
        "reason": str(reason or ""),
        "note": str(note or ""),
        "reviewerId": str(user.id),
        "reviewedAt": reviewed_at.isoformat(),
        "deadlineAt": parsed_deadline.isoformat() if parsed_deadline else None,
        "failedItems": [
            {key: value for key, value in entry.items() if key != "item"}
            for entry in normalized_failed_items
        ],
        "mediaIds": [str(photo.id) for photo in qc_media],
        "taskVersion": task.version,
    }
    qc_task.save(
        update_fields=[
            "status",
            "reviewer",
            "reason",
            "note",
            "reviewed_at",
            "deadline_at",
            "result_snapshot",
        ]
    )
    if qc_media:
        TaskPhoto.objects.filter(pk__in=[photo.pk for photo in qc_media]).update(qc_round=qc_task)
    if approved:
        if task.issues.exclude(status__in={IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED}).filter(
            blocks_room_ready=True
        ).exists():
            raise HousekeepingError("BLOCKING_ISSUE_EXISTS", "Còn sự cố chặn phòng chưa xử lý.", status=409)
        status = HousekeepingTask.Status.QC_APPROVED
        action = "TASK_QC_APPROVED"
        transition_action = Action.QC_APPROVE
        task.rework_rounds.select_for_update().filter(status=ReworkRound.Status.SENT_TO_QC).update(
            status=ReworkRound.Status.COMPLETED,
            completed_at=reviewed_at,
        )
    else:
        failed_only = bool(normalized_failed_items)
        try:
            failed_only = failed_only and task.branch.housekeeping_policy.rework_failed_items_only
        except BranchHousekeepingPolicy.DoesNotExist:
            pass
        task.rework_rounds.select_for_update().filter(status=ReworkRound.Status.SENT_TO_QC).update(
            status=ReworkRound.Status.COMPLETED,
            completed_at=reviewed_at,
        )
        rework_round = ReworkRound.objects.create(
            task=task,
            source_qc_round=qc_task,
            round_number=task.rework_rounds.count() + 1,
            failed_items_only=failed_only,
            checklist_snapshot=(
                qc_task.result_snapshot["failedItems"]
                if normalized_failed_items
                else qc_task.checklist_snapshot
            ),
        )
        for entry in normalized_failed_items:
            failed = QCFailedItem.objects.create(
                qc_round=qc_task,
                checklist_item=entry["item"],
                reason_code=entry["reasonCode"],
                reason=entry["reason"],
                note=entry["note"],
                rework_required=entry["reworkRequired"],
                resolved_in_rework=rework_round,
            )
            if failed.rework_required:
                TaskChecklistItem.objects.filter(pk=failed.checklist_item_id).update(
                    status=TaskChecklistItem.Status.PENDING,
                    completed_by=None,
                    completed_at=None,
                    update_version=F("update_version") + 1,
                )
        task.current_rework_round = rework_round.round_number
        task.progress_percent = _recalculate_progress(task)
        task.updated_by = user
        task.last_progress_at = reviewed_at
        status = HousekeepingTask.Status.QC_REJECTED
        action = "TASK_QC_REJECTED"
        transition_action = Action.QC_REJECT
    _transition(
        task,
        user,
        status,
        action,
        context,
        transition_action=transition_action,
        reason_code="QC_REJECTED" if not approved else "",
        note=reason or "",
        changes={
            "qcRound": qc_task.round_number,
            "failedItemCount": len(normalized_failed_items),
            "mediaCount": len(qc_media),
            "deadlineAt": parsed_deadline.isoformat() if parsed_deadline else None,
        },
        update_fields=(
            ["current_rework_round", "progress_percent", "updated_by", "last_progress_at"]
            if not approved
            else None
        ),
    )
    if approved:
        task.assignments.filter(is_current=True).update(
            status=TaskAssignment.Status.ENDED,
            is_current=False,
            ended_at=timezone.now(),
        )
        notify_task(
            task,
            "QC_APPROVED",
            f"Kiểm tra chất lượng đạt: phòng {task.room.code}",
            f"Công việc {task.code} đã được duyệt ở vòng kiểm tra thứ {qc_task.round_number}.",
            deduplication_key=f"task:{task.id}:qc:{qc_task.round_number}:approved",
            users=[task.assignee] if task.assignee else None,
            roles={"housekeeping_lead"},
            payload={"taskId": str(task.id), "qcRound": qc_task.round_number},
        )
    else:
        notify_task(
            task,
            "QC_REJECTED",
            f"Kiểm tra chất lượng chưa đạt: phòng {task.room.code}",
            str(reason or "Công việc cần được làm lại."),
            deduplication_key=f"task:{task.id}:qc:{qc_task.round_number}:rejected",
            users=[task.assignee] if task.assignee else None,
            roles={"housekeeping_lead"},
            payload={
                "taskId": str(task.id),
                "qcRound": qc_task.round_number,
                "deadlineAt": parsed_deadline.isoformat() if parsed_deadline else None,
                "failedItemCount": len(normalized_failed_items),
            },
        )
    return task, qc_task


@transaction.atomic
def reject_task(user, task_id, version, reason_code, note, context):
    if not str(reason_code or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Vui lòng chọn lý do từ chối công việc.")
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.RETURN)
    _check_version(task, version)
    if task.assignee_id != user.id or task.status not in {
        HousekeepingTask.Status.ASSIGNED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE,
    }:
        raise HousekeepingError("TASK_INVALID_STATUS", "Không thể từ chối công việc ở trạng thái hiện tại.", status=409)
    task.assignee = None
    task.accepted_at = None
    _transition(
        task,
        user,
        HousekeepingTask.Status.UNASSIGNED,
        "TASK_REJECTED",
        context,
        transition_action=Action.REJECT,
        reason_code=str(reason_code),
        note=str(note or ""),
        update_fields=["assignee", "accepted_at"],
    )
    task.assignments.filter(is_current=True).update(
        status=TaskAssignment.Status.REJECTED,
        is_current=False,
        reason_code=str(reason_code),
        note=str(note or ""),
        ended_at=timezone.now(),
    )
    return task


@transaction.atomic
def reassign_task(user, task_id, assignee_id, version, context, *, shift_id=None, reason_code="", note=""):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.ASSIGN)
    _check_version(task, version)
    try:
        assignee = User.objects.get(pk=assignee_id, is_active=True, is_deleted=False)
    except (User.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_ACCESS_DENIED", "Không tìm thấy nhân viên được phân công.", status=404) from None
    target_membership = membership_for(assignee, task.branch_id)
    if target_membership is None:
        raise HousekeepingError("USER_BRANCH_NOT_ALLOWED", "Nhân viên không thuộc chi nhánh của công việc.", status=403)
    if not membership_covers_task(target_membership, task):
        raise HousekeepingError("TASK_ACCESS_DENIED", "Nhân viên không thuộc nhóm hoặc khu vực của công việc.", status=403)
    if not membership_has_task_skills(target_membership, task):
        raise HousekeepingError(
            "TASK_SKILL_NOT_ALLOWED",
            "Nhân viên chưa có đủ kỹ năng bắt buộc của công việc.",
            status=403,
        )
    shift = task.shift
    if shift_id:
        try:
            shift = Shift.objects.get(pk=shift_id, branch_id=task.branch_id, is_active=True)
        except (Shift.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Ca phân công không hợp lệ.", status=400) from None

    now = timezone.now()
    task.assignments.select_for_update().filter(is_current=True).update(
        status=TaskAssignment.Status.REASSIGNED,
        is_current=False,
        reason_code=str(reason_code or ""),
        note=str(note or ""),
        ended_at=now,
    )
    previous_assignee_id = task.assignee_id
    task.assignee = assignee
    task.assigned_by = user
    task.accepted_at = None
    task.shift = shift
    if target_membership.team_id:
        task.team_id = target_membership.team_id
    _transition(
        task,
        user,
        HousekeepingTask.Status.PENDING_ACCEPTANCE,
        "TASK_REASSIGNED",
        context,
        transition_action=Action.REASSIGN,
        reason_code=str(reason_code or ""),
        note=str(note or ""),
        changes={"fromAssigneeId": str(previous_assignee_id or ""), "toAssigneeId": str(assignee.id)},
        update_fields=["assignee", "assigned_by", "accepted_at", "shift", "team"],
    )
    TaskAssignment.objects.create(
        task=task,
        assignee=assignee,
        assigned_by=user,
        shift=shift,
        team=task.team,
        status=TaskAssignment.Status.PENDING,
        reason_code=str(reason_code or ""),
        note=str(note or ""),
    )
    notify_task(
        task,
        "TASK_ASSIGNED",
        f"Bạn được giao công việc {task.code}",
        f"Phòng {task.room.code} đang chờ bạn nhận việc.",
        deduplication_key=f"task:{task.id}:assigned:{assignee.id}:v{task.version}",
        users=[assignee],
        payload={"taskId": str(task.id), "taskVersion": task.version},
    )
    return task


@transaction.atomic
def handover_task(
    user,
    task_id,
    recipient_id,
    version,
    context,
    *,
    to_shift_id=None,
    note="",
    reconfirm_required_items=None,
):
    try:
        before = HousekeepingTask.objects.select_for_update().get(pk=task_id)
    except (HousekeepingTask.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy công việc.", status=404) from None
    from_assignment = before.assignments.filter(is_current=True).order_by("-assigned_at").first()
    from_user = before.assignee
    from_shift = before.shift
    task = reassign_task(
        user,
        task_id,
        recipient_id,
        version,
        context,
        shift_id=to_shift_id,
        reason_code="SHIFT_HANDOVER",
        note=note,
    )
    to_assignment = task.assignments.filter(is_current=True).order_by("-assigned_at").first()
    TaskHandover.objects.create(
        task=task,
        from_assignment=from_assignment,
        to_assignment=to_assignment,
        from_user=from_user,
        to_user=task.assignee,
        from_shift=from_shift,
        to_shift=task.shift,
        note=str(note or ""),
        reconfirm_required_items=reconfirm_required_items or [],
        handed_over_by=user,
    )
    return task


@transaction.atomic
def cancel_task(user, task_id, version, reason, context):
    reason = str(reason or "").strip()
    if not reason:
        raise HousekeepingError("TASK_INVALID_STATUS", "Hủy công việc phải có lý do.")
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.CANCEL)
    _check_version(task, version)
    task.cancelled_at = timezone.now()
    task.cancelled_by = user
    task.cancellation_reason = reason
    task.assignments.select_for_update().filter(is_current=True).update(
        status=TaskAssignment.Status.ENDED,
        is_current=False,
        reason_code="TASK_CANCELLED",
        note=reason,
        ended_at=task.cancelled_at,
    )
    _transition(
        task,
        user,
        HousekeepingTask.Status.CANCELLED,
        "TASK_CANCELLED",
        context,
        transition_action=Action.CANCEL,
        reason_code="TASK_CANCELLED",
        note=reason,
        update_fields=["cancelled_at", "cancelled_by", "cancellation_reason"],
    )
    notify_task(
        task,
        "TASK_CANCELLED",
        f"Công việc {task.code} đã bị hủy",
        reason,
        deduplication_key=f"task:{task.id}:cancelled:v{task.version}",
        users=[task.assignee] if task.assignee else None,
        roles={"housekeeping_lead"},
        payload={"taskId": str(task.id), "reason": reason},
    )
    return task


@transaction.atomic
def change_task_priority(user, task_id, version, priority, reason, context):
    task = _get_task(user, task_id, lock=True)
    _require_capability(user, task, Capability.CHANGE_PRIORITY)
    _check_version(task, version)
    if priority not in HousekeepingTask.Priority.values:
        raise HousekeepingError("TASK_INVALID_STATUS", "Mức ưu tiên không hợp lệ.")
    old_priority = task.priority
    task.priority = priority
    task.version += 1
    task.updated_by = user
    task.save(update_fields=["priority", "version", "updated_by", "updated_at"])
    _log(
        task,
        user,
        "TASK_PRIORITY_CHANGED",
        context,
        changes={"from": old_priority, "to": priority, "reason": str(reason or "")},
    )
    return task


SUPPLY_QUEUE_ROLES = MANAGEMENT_ROLES | {User.Role.WAREHOUSE}
ISSUE_QUEUE_ROLES = MANAGEMENT_ROLES | {User.Role.TECHNICIAN}


def scoped_supply_requests(user):
    _ensure_role(user, SUPPLY_QUEUE_ROLES)
    queryset = SupplyRequest.objects.select_related(
        "task",
        "task__room",
        "branch",
        "destination",
        "requested_by",
        "resolved_by",
    ).prefetch_related("items")
    branch_ids = allowed_branch_ids(user)
    return queryset if branch_ids is None else queryset.filter(branch_id__in=branch_ids)


def scoped_issues(user):
    _ensure_role(user, ISSUE_QUEUE_ROLES)
    queryset = IssueTicket.objects.select_related(
        "task",
        "task__room",
        "room",
        "booking",
        "reported_by",
        "assigned_to",
        "resolved_by",
    )
    branch_ids = allowed_branch_ids(user)
    return queryset if branch_ids is None else queryset.filter(task__branch_id__in=branch_ids)


def _check_entity_version(entity, version, *, label):
    try:
        requested = int(version)
    except (TypeError, ValueError):
        raise HousekeepingError("TASK_VERSION_CONFLICT", f"Thiếu hoặc sai phiên bản {label}.", status=409) from None
    if entity.version != requested:
        raise HousekeepingError(
            "TASK_VERSION_CONFLICT",
            f"{label} đã được cập nhật bởi người khác.",
            status=409,
            details={"currentVersion": entity.version},
        )


def _touch_task_for_support(task, user, event, context, changes):
    task.version += 1
    task.updated_by = user
    task.last_progress_at = timezone.now()
    task.save(update_fields=["version", "updated_by", "last_progress_at", "updated_at"])
    _log(task, user, event, context, changes=changes)


@transaction.atomic
def update_supply_request_status(user, request_id, version, status, note, context):
    try:
        supply = scoped_supply_requests(user).select_for_update().get(pk=request_id)
    except (SupplyRequest.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy yêu cầu vật tư.", status=404) from None
    _check_entity_version(supply, version, label="Yêu cầu vật tư")
    transitions = {
        SupplyRequest.Status.PENDING: {
            SupplyRequest.Status.ACKNOWLEDGED,
            SupplyRequest.Status.REJECTED,
            SupplyRequest.Status.CANCELLED,
        },
        SupplyRequest.Status.ACKNOWLEDGED: {
            SupplyRequest.Status.FULFILLED,
            SupplyRequest.Status.REJECTED,
            SupplyRequest.Status.CANCELLED,
        },
    }
    if status not in transitions.get(supply.status, set()):
        raise HousekeepingError("TASK_INVALID_STATUS", "Không thể chuyển trạng thái yêu cầu vật tư.", status=409)
    if status in {SupplyRequest.Status.REJECTED, SupplyRequest.Status.CANCELLED} and not str(note or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Từ chối/hủy yêu cầu vật tư phải có lý do.")
    previous_status = supply.status
    now = timezone.now()
    supply.status = status
    supply.version += 1
    fields = ["status", "version"]
    if status == SupplyRequest.Status.ACKNOWLEDGED:
        supply.acknowledged_at = now
        fields.append("acknowledged_at")
    if status in {
        SupplyRequest.Status.FULFILLED,
        SupplyRequest.Status.REJECTED,
        SupplyRequest.Status.CANCELLED,
    }:
        supply.resolved_by = user
        supply.resolved_at = now
        supply.resolution_note = str(note or "")
        fields.extend(["resolved_by", "resolved_at", "resolution_note"])
    supply.save(update_fields=fields)
    _touch_task_for_support(
        supply.task,
        user,
        "SUPPLY_REQUEST_STATUS_CHANGED",
        context,
        {
            "requestId": str(supply.id),
            "from": previous_status,
            "to": status,
            "requestVersion": supply.version,
        },
    )
    notify_task(
        supply.task,
        "SUPPLY_REQUEST_UPDATED",
        f"Vật tư phòng {supply.task.room.code}: {supply.get_status_display()}",
        str(note or "Yêu cầu vật tư đã được cập nhật."),
        deduplication_key=f"supply:{supply.id}:status:{status}:v{supply.version}",
        users=[supply.requested_by] if supply.requested_by else None,
        payload={
            "taskId": str(supply.task_id),
            "supplyRequestId": str(supply.id),
            "status": status,
        },
    )
    return supply, supply.task


@transaction.atomic
def update_issue_status(user, issue_id, version, status, note, context, *, assigned_to_id=None):
    try:
        issue = scoped_issues(user).select_for_update().get(pk=issue_id)
    except (IssueTicket.DoesNotExist, ValueError):
        raise HousekeepingError("TASK_NOT_FOUND", "Không tìm thấy phiếu sự cố.", status=404) from None
    _check_entity_version(issue, version, label="Phiếu sự cố")
    transitions = {
        IssueTicket.Status.OPEN: {
            IssueTicket.Status.ASSIGNED,
            IssueTicket.Status.IN_PROGRESS,
            IssueTicket.Status.RESOLVED,
            IssueTicket.Status.CANCELLED,
        },
        IssueTicket.Status.ASSIGNED: {
            IssueTicket.Status.IN_PROGRESS,
            IssueTicket.Status.RESOLVED,
            IssueTicket.Status.CANCELLED,
        },
        IssueTicket.Status.IN_PROGRESS: {
            IssueTicket.Status.RESOLVED,
            IssueTicket.Status.CANCELLED,
        },
    }
    if status not in transitions.get(issue.status, set()):
        raise HousekeepingError("TASK_INVALID_STATUS", "Không thể chuyển trạng thái phiếu sự cố.", status=409)
    if status in {IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED} and not str(note or "").strip():
        raise HousekeepingError("TASK_INVALID_STATUS", "Đóng phiếu sự cố phải có ghi chú xử lý.")
    assignee = issue.assigned_to
    if assigned_to_id:
        try:
            assignee = User.objects.get(
                pk=assigned_to_id,
                role=User.Role.TECHNICIAN,
                is_active=True,
                is_deleted=False,
            )
        except (User.DoesNotExist, ValueError):
            raise HousekeepingError("TASK_ACCESS_DENIED", "Kỹ thuật viên được giao không hợp lệ.", status=404) from None
        assignee_branches = allowed_branch_ids(assignee)
        if assignee_branches is not None and issue.task.branch_id not in assignee_branches:
            raise HousekeepingError("USER_BRANCH_NOT_ALLOWED", "Kỹ thuật viên không thuộc chi nhánh.", status=403)
    if status == IssueTicket.Status.ASSIGNED and assignee is None:
        raise HousekeepingError("TASK_ACCESS_DENIED", "Cần chọn kỹ thuật viên xử lý.")
    previous_status = issue.status
    now = timezone.now()
    issue.status = status
    issue.version += 1
    fields = ["status", "version"]
    if assignee and assignee != issue.assigned_to:
        issue.assigned_to = assignee
        issue.assigned_at = now
        fields.extend(["assigned_to", "assigned_at"])
    if status == IssueTicket.Status.IN_PROGRESS and issue.assigned_at is None:
        issue.assigned_at = now
        fields.append("assigned_at")
    if status in {IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED}:
        issue.resolved_by = user
        issue.resolved_at = now
        issue.resolution_note = str(note or "")
        fields.extend(["resolved_by", "resolved_at", "resolution_note"])
    issue.save(update_fields=fields)
    _touch_task_for_support(
        issue.task,
        user,
        "ISSUE_STATUS_CHANGED",
        context,
        {
            "issueId": str(issue.id),
            "from": previous_status,
            "to": status,
            "issueVersion": issue.version,
            "assignedToId": str(issue.assigned_to_id or ""),
        },
    )
    recipients = [candidate for candidate in (issue.reported_by, issue.assigned_to) if candidate]
    notify_task(
        issue.task,
        "ISSUE_UPDATED",
        f"Sự cố phòng {issue.room.code}: {issue.get_status_display()}",
        str(note or "Phiếu sự cố đã được cập nhật."),
        deduplication_key=f"issue:{issue.id}:status:{status}:v{issue.version}",
        users=recipients,
        payload={"taskId": str(issue.task_id), "issueId": str(issue.id), "status": status},
    )
    return issue, issue.task
