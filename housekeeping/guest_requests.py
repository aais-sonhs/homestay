"""Domain services and scoped queries for in-stay guest requests."""

import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.models import User
from common.access import GLOBAL_ROLES, active_memberships, is_active_user
from organizations.models import Branch, BranchMembership, Room
from organizations.selectors import branch_queryset_for_user

from .models import Booking, GuestServiceRequest, GuestServiceRequestEvent
from .notifications import notify_guest_request
from .services import HousekeepingError


CREATOR_ROLES = GLOBAL_ROLES | {
    User.Role.BRANCH_OWNER,
    User.Role.MANAGER,
    User.Role.CUSTOMER_SERVICE,
}
MANAGER_ROLES = GLOBAL_ROLES | {User.Role.BRANCH_OWNER, User.Role.MANAGER}
TERMINAL_STATUSES = {
    GuestServiceRequest.Status.COMPLETED,
    GuestServiceRequest.Status.CANCELLED,
}


def _branch_ids(user):
    if user.role in GLOBAL_ROLES:
        return None
    return list(branch_queryset_for_user(user).values_list("id", flat=True))


def guest_request_queryset_for_user(user):
    queryset = GuestServiceRequest.objects.select_related(
        "branch",
        "room",
        "booking",
        "requested_by",
        "assignee",
        "assigned_by",
    )
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset

    memberships = list(active_memberships(user))
    if user.role in {
        User.Role.BRANCH_OWNER,
        User.Role.MANAGER,
        User.Role.CUSTOMER_SERVICE,
    }:
        return queryset.filter(branch_id__in=_branch_ids(user) or [])
    if user.role != User.Role.HOUSEKEEPING:
        return queryset.none()

    worker_scope = Q(pk__in=[])
    for membership in memberships:
        if membership.membership_role not in {
            BranchMembership.MembershipRole.HOUSEKEEPER,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        }:
            continue
        scope = Q(branch_id=membership.branch_id) & (
            Q(assignee=user)
            | Q(
                assignee__isnull=True,
                status=GuestServiceRequest.Status.NEW,
            )
        )
        area_ids = list(membership.areas.values_list("id", flat=True))
        if area_ids:
            scope &= Q(room__area_ref_id__in=area_ids)
        elif membership.area:
            scope &= Q(room__area=membership.area)
        worker_scope |= scope
    return queryset.filter(worker_scope).distinct()


def filtered_guest_request_queryset(user, params):
    queryset = guest_request_queryset_for_user(user)
    branch_id = str(params.get("branchId") or "").strip()
    if branch_id:
        try:
            queryset = queryset.filter(branch_id=uuid.UUID(branch_id))
        except ValueError:
            return queryset.none()

    status = str(params.get("status") or "").strip().upper()
    if status:
        if status not in GuestServiceRequest.Status.values:
            raise HousekeepingError("SYSTEM_ERROR", "Trạng thái yêu cầu không hợp lệ.")
        queryset = queryset.filter(status=status)
    request_type = str(params.get("requestType") or "").strip().upper()
    if request_type:
        if request_type not in GuestServiceRequest.RequestType.values:
            raise HousekeepingError("SYSTEM_ERROR", "Loại yêu cầu không hợp lệ.")
        queryset = queryset.filter(request_type=request_type)

    tab = str(params.get("tab") or "").strip().lower()
    if tab == "mine":
        queryset = queryset.filter(assignee=user)
    elif tab == "open":
        queryset = queryset.filter(
            assignee__isnull=True,
            status=GuestServiceRequest.Status.NEW,
        )
    elif tab == "in-progress":
        queryset = queryset.filter(
            status__in={
                GuestServiceRequest.Status.ACCEPTED,
                GuestServiceRequest.Status.IN_PROGRESS,
            }
        )
    elif tab == "done":
        queryset = queryset.filter(status=GuestServiceRequest.Status.COMPLETED)
    elif tab == "cancelled":
        queryset = queryset.filter(status=GuestServiceRequest.Status.CANCELLED)
    elif not status:
        queryset = queryset.exclude(status__in=TERMINAL_STATUSES)

    overdue = str(params.get("overdue") or "").lower()
    if overdue in {"1", "true", "yes", "on"}:
        queryset = queryset.filter(due_at__lt=timezone.now()).exclude(
            status__in=TERMINAL_STATUSES
        )
    query = str(params.get("q") or "").strip()
    if query:
        search = (
            Q(code__icontains=query)
            | Q(room__code__icontains=query)
            | Q(room__name__icontains=query)
            | Q(booking__code__icontains=query)
            | Q(description__icontains=query)
        )
        if user.role in CREATOR_ROLES:
            search |= Q(booking__guest_name__icontains=query) | Q(
                booking__guest_phone__icontains=query
            )
        queryset = queryset.filter(search)
    return queryset.order_by("due_at", "-priority", "created_at")


def guest_request_for_user(user, request_id, *, lock=False):
    queryset = guest_request_queryset_for_user(user)
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=request_id)
    except (GuestServiceRequest.DoesNotExist, ValueError):
        raise HousekeepingError(
            "GUEST_REQUEST_NOT_FOUND",
            "Không tìm thấy yêu cầu khách lưu trú.",
            status=404,
        ) from None


def _ensure_creator(user):
    if not is_active_user(user) or user.role not in CREATOR_ROLES:
        raise HousekeepingError(
            "GUEST_REQUEST_ACCESS_DENIED",
            "Bạn không có quyền tạo yêu cầu khách lưu trú.",
            status=403,
        )


def _ensure_manager(user, branch_id):
    if not is_active_user(user) or user.role not in MANAGER_ROLES:
        raise HousekeepingError(
            "GUEST_REQUEST_ACCESS_DENIED",
            "Bạn không có quyền điều phối yêu cầu này.",
            status=403,
        )
    if user.role not in GLOBAL_ROLES and branch_id not in (_branch_ids(user) or []):
        raise HousekeepingError(
            "USER_BRANCH_NOT_ALLOWED",
            "Bạn không có quyền tại chi nhánh này.",
            status=403,
        )


def _check_version(item, version):
    try:
        requested_version = int(version)
    except (TypeError, ValueError):
        raise HousekeepingError(
            "GUEST_REQUEST_VERSION_CONFLICT",
            "Thiếu hoặc sai phiên bản yêu cầu.",
            status=409,
        ) from None
    if item.version != requested_version:
        raise HousekeepingError(
            "GUEST_REQUEST_VERSION_CONFLICT",
            "Yêu cầu đã được cập nhật bởi người khác. Vui lòng tải lại.",
            status=409,
        )


def _parse_due_at(value, priority):
    if value:
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise HousekeepingError(
                "GUEST_REQUEST_INVALID",
                "Hạn hoàn thành không hợp lệ.",
            )
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        if parsed <= timezone.now():
            raise HousekeepingError(
                "GUEST_REQUEST_INVALID",
                "Hạn hoàn thành phải ở tương lai.",
            )
        return parsed
    minutes = {
        GuestServiceRequest.Priority.URGENT: 10,
        GuestServiceRequest.Priority.HIGH: 15,
        GuestServiceRequest.Priority.NORMAL: 20,
        GuestServiceRequest.Priority.LOW: 30,
    }[priority]
    return timezone.now() + timedelta(minutes=minutes)


def _event(item, user, action, from_status="", note="", metadata=None):
    GuestServiceRequestEvent.objects.create(
        request=item,
        user=user,
        action=action,
        from_status=from_status,
        to_status=item.status,
        note=str(note or ""),
        metadata=metadata or {},
    )


def _next_code():
    day = timezone.localdate().strftime("%y%m%d")
    while True:
        code = f"YC-{day}-{uuid.uuid4().hex[:6].upper()}"
        if not GuestServiceRequest.objects.filter(code=code).exists():
            return code


def _eligible_assignee(branch, assignee_id):
    try:
        assignee = User.objects.get(
            pk=assignee_id,
            is_active=True,
            is_deleted=False,
            role=User.Role.HOUSEKEEPING,
        )
    except (User.DoesNotExist, ValueError):
        raise HousekeepingError(
            "GUEST_REQUEST_ASSIGNEE_INVALID",
            "Nhân viên thực hiện không hợp lệ.",
        ) from None
    membership = active_memberships(assignee).filter(
        branch=branch,
        membership_role__in={
            BranchMembership.MembershipRole.HOUSEKEEPER,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        },
    ).first()
    if membership is None:
        raise HousekeepingError(
            "GUEST_REQUEST_ASSIGNEE_INVALID",
            "Nhân viên không thuộc bộ phận buồng phòng của chi nhánh.",
        )
    return assignee


@transaction.atomic
def create_guest_request(user, payload):
    _ensure_creator(user)
    try:
        branch = Branch.objects.get(pk=payload.get("branchId"), is_active=True)
    except (Branch.DoesNotExist, ValueError, TypeError):
        raise HousekeepingError(
            "USER_BRANCH_NOT_ALLOWED", "Chi nhánh không hợp lệ.", status=403
        ) from None
    if user.role not in GLOBAL_ROLES and branch.id not in (_branch_ids(user) or []):
        raise HousekeepingError(
            "USER_BRANCH_NOT_ALLOWED",
            "Bạn không có quyền tại chi nhánh này.",
            status=403,
        )
    try:
        room = Room.objects.get(pk=payload.get("roomId"), branch=branch)
    except (Room.DoesNotExist, ValueError, TypeError):
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID", "Phòng không thuộc chi nhánh đã chọn."
        ) from None
    try:
        booking = Booking.objects.get(
            pk=payload.get("bookingId"),
            branch=branch,
            room=room,
            status=Booking.Status.CHECKED_IN,
        )
    except (Booking.DoesNotExist, ValueError, TypeError):
        raise HousekeepingError(
            "GUEST_REQUEST_BOOKING_INVALID",
            "Chỉ có thể tạo yêu cầu cho booking đang nhận phòng tại phòng đã chọn.",
        ) from None

    request_type = str(payload.get("requestType") or "").strip().upper()
    if request_type not in GuestServiceRequest.RequestType.values:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Loại yêu cầu không hợp lệ.")
    priority = str(
        payload.get("priority") or GuestServiceRequest.Priority.NORMAL
    ).strip().upper()
    if priority not in GuestServiceRequest.Priority.values:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Mức ưu tiên không hợp lệ.")
    source = str(
        payload.get("source") or GuestServiceRequest.Source.ZALO
    ).strip().upper()
    if source not in GuestServiceRequest.Source.values:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Kênh tiếp nhận không hợp lệ.")
    description = str(payload.get("description") or "").strip()
    if not description:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Vui lòng nhập nội dung khách yêu cầu.")
    try:
        quantity = int(payload.get("quantity") or 1)
    except (TypeError, ValueError):
        quantity = 0
    if quantity < 1 or quantity > 999:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Số lượng phải từ 1 đến 999.")

    assignee = None
    assignee_id = payload.get("assigneeId")
    if assignee_id:
        _ensure_manager(user, branch.id)
        assignee = _eligible_assignee(branch, assignee_id)
    item = GuestServiceRequest.objects.create(
        code=_next_code(),
        branch=branch,
        room=room,
        booking=booking,
        request_type=request_type,
        description=description,
        quantity=quantity,
        unit=str(payload.get("unit") or "").strip()[:30],
        source=source,
        priority=priority,
        status=(
            GuestServiceRequest.Status.ASSIGNED
            if assignee
            else GuestServiceRequest.Status.NEW
        ),
        requested_by=user,
        assignee=assignee,
        assigned_by=user if assignee else None,
        due_at=_parse_due_at(payload.get("dueAt"), priority),
    )
    _event(
        item,
        user,
        "GUEST_REQUEST_CREATED",
        metadata={"source": source, "assigneeId": str(assignee.id) if assignee else None},
    )
    if assignee:
        notify_guest_request(
            item,
            "GUEST_REQUEST_ASSIGNED",
            f"Khách phòng {room.code} cần hỗ trợ",
            description,
            deduplication_key=f"guest-request:{item.id}:assigned:v{item.version}",
            users=[assignee],
        )
    else:
        notify_guest_request(
            item,
            "GUEST_REQUEST_CREATED",
            f"Yêu cầu mới từ phòng {room.code}",
            description,
            deduplication_key=f"guest-request:{item.id}:created",
            roles={"manager", "housekeeping_lead", "housekeeping"},
        )
    return item


@transaction.atomic
def assign_guest_request(user, request_id, assignee_id, version, note=""):
    item = guest_request_for_user(user, request_id, lock=True)
    _ensure_manager(user, item.branch_id)
    _check_version(item, version)
    if item.status in TERMINAL_STATUSES or item.status == GuestServiceRequest.Status.IN_PROGRESS:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_STATUS",
            "Không thể phân công yêu cầu ở trạng thái hiện tại.",
            status=409,
        )
    assignee = _eligible_assignee(item.branch, assignee_id)
    old_status = item.status
    old_assignee_id = item.assignee_id
    item.assignee = assignee
    item.assigned_by = user
    item.status = GuestServiceRequest.Status.ASSIGNED
    item.accepted_at = None
    item.started_at = None
    item.version += 1
    item.save(
        update_fields=[
            "assignee",
            "assigned_by",
            "status",
            "accepted_at",
            "started_at",
            "version",
            "updated_at",
        ]
    )
    _event(
        item,
        user,
        "GUEST_REQUEST_ASSIGNED",
        old_status,
        note,
        {"fromAssigneeId": str(old_assignee_id or ""), "toAssigneeId": str(assignee.id)},
    )
    notify_guest_request(
        item,
        "GUEST_REQUEST_ASSIGNED",
        f"Khách phòng {item.room.code} cần hỗ trợ",
        item.description,
        deduplication_key=f"guest-request:{item.id}:assigned:v{item.version}",
        users=[assignee],
    )
    return item


def _worker_membership(user, item):
    if user.role != User.Role.HOUSEKEEPING:
        return None
    return active_memberships(user).filter(
        branch_id=item.branch_id,
        membership_role__in={
            BranchMembership.MembershipRole.HOUSEKEEPER,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        },
    ).first()


@transaction.atomic
def accept_guest_request(user, request_id, version):
    item = guest_request_for_user(user, request_id, lock=True)
    _check_version(item, version)
    if _worker_membership(user, item) is None:
        raise HousekeepingError(
            "GUEST_REQUEST_ACCESS_DENIED", "Bạn không thể nhận yêu cầu này.", status=403
        )
    if item.status not in {
        GuestServiceRequest.Status.NEW,
        GuestServiceRequest.Status.ASSIGNED,
    } or item.assignee_id not in {None, user.id}:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_STATUS",
            "Yêu cầu đã được người khác nhận hoặc không còn chờ nhận.",
            status=409,
        )
    old_status = item.status
    item.assignee = user
    item.status = GuestServiceRequest.Status.ACCEPTED
    item.accepted_at = timezone.now()
    item.version += 1
    item.save(
        update_fields=["assignee", "status", "accepted_at", "version", "updated_at"]
    )
    _event(item, user, "GUEST_REQUEST_ACCEPTED", old_status)
    return item


@transaction.atomic
def start_guest_request(user, request_id, version):
    item = guest_request_for_user(user, request_id, lock=True)
    _check_version(item, version)
    if item.assignee_id != user.id or item.status != GuestServiceRequest.Status.ACCEPTED:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_STATUS",
            "Bạn chưa nhận hoặc không phải người thực hiện yêu cầu này.",
            status=409,
        )
    old_status = item.status
    item.status = GuestServiceRequest.Status.IN_PROGRESS
    item.started_at = timezone.now()
    item.version += 1
    item.save(update_fields=["status", "started_at", "version", "updated_at"])
    _event(item, user, "GUEST_REQUEST_STARTED", old_status)
    return item


@transaction.atomic
def complete_guest_request(user, request_id, version, note=""):
    item = guest_request_for_user(user, request_id, lock=True)
    _check_version(item, version)
    if item.assignee_id != user.id or item.status != GuestServiceRequest.Status.IN_PROGRESS:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_STATUS",
            "Chỉ người đang thực hiện mới có thể hoàn thành yêu cầu.",
            status=409,
        )
    old_status = item.status
    item.status = GuestServiceRequest.Status.COMPLETED
    item.completed_at = timezone.now()
    item.resolution_note = str(note or "").strip()
    item.version += 1
    item.save(
        update_fields=[
            "status",
            "completed_at",
            "resolution_note",
            "version",
            "updated_at",
        ]
    )
    _event(item, user, "GUEST_REQUEST_COMPLETED", old_status, note)
    notify_guest_request(
        item,
        "GUEST_REQUEST_COMPLETED",
        f"Đã phục vụ phòng {item.room.code}",
        item.description,
        deduplication_key=f"guest-request:{item.id}:completed",
        users=[item.requested_by] if item.requested_by else None,
        roles={"manager"},
    )
    return item


@transaction.atomic
def cancel_guest_request(user, request_id, version, reason):
    item = guest_request_for_user(user, request_id, lock=True)
    _check_version(item, version)
    reason = str(reason or "").strip()
    if not reason:
        raise HousekeepingError("GUEST_REQUEST_INVALID", "Vui lòng nhập lý do hủy.")
    is_manager = user.role in MANAGER_ROLES
    is_creator = user.role == User.Role.CUSTOMER_SERVICE and item.requested_by_id == user.id
    if not is_manager and not is_creator:
        raise HousekeepingError(
            "GUEST_REQUEST_ACCESS_DENIED", "Bạn không có quyền hủy yêu cầu này.", status=403
        )
    if item.status in TERMINAL_STATUSES:
        raise HousekeepingError(
            "GUEST_REQUEST_INVALID_STATUS", "Yêu cầu đã kết thúc.", status=409
        )
    old_status = item.status
    previous_assignee = item.assignee
    item.status = GuestServiceRequest.Status.CANCELLED
    item.cancelled_at = timezone.now()
    item.cancellation_reason = reason
    item.version += 1
    item.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancellation_reason",
            "version",
            "updated_at",
        ]
    )
    _event(item, user, "GUEST_REQUEST_CANCELLED", old_status, reason)
    notify_guest_request(
        item,
        "GUEST_REQUEST_CANCELLED",
        f"Yêu cầu phòng {item.room.code} đã hủy",
        reason,
        deduplication_key=f"guest-request:{item.id}:cancelled",
        users=[previous_assignee] if previous_assignee else None,
    )
    return item


def guest_request_capabilities(user, item):
    is_worker = user.role == User.Role.HOUSEKEEPING
    is_assignee = item.assignee_id == user.id
    is_manager = user.role in MANAGER_ROLES
    is_creator = user.role == User.Role.CUSTOMER_SERVICE and item.requested_by_id == user.id
    return {
        "accept": is_worker
        and item.status in {GuestServiceRequest.Status.NEW, GuestServiceRequest.Status.ASSIGNED}
        and item.assignee_id in {None, user.id},
        "start": is_assignee and item.status == GuestServiceRequest.Status.ACCEPTED,
        "complete": is_assignee and item.status == GuestServiceRequest.Status.IN_PROGRESS,
        "assign": is_manager
        and item.status
        in {
            GuestServiceRequest.Status.NEW,
            GuestServiceRequest.Status.ASSIGNED,
            GuestServiceRequest.Status.ACCEPTED,
        },
        "cancel": (is_manager or is_creator) and item.status not in TERMINAL_STATUSES,
    }


def eligible_housekeepers(user):
    branch_ids = _branch_ids(user)
    queryset = User.objects.filter(
        is_active=True,
        is_deleted=False,
        role=User.Role.HOUSEKEEPING,
        branch_memberships__is_active=True,
        branch_memberships__membership_role__in={
            BranchMembership.MembershipRole.HOUSEKEEPER,
            BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        },
    ).select_related()
    if branch_ids is not None:
        queryset = queryset.filter(branch_memberships__branch_id__in=branch_ids)
    return queryset.distinct().order_by("first_name", "username")
