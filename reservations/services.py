import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from housekeeping.models import Booking, BookingChangeLog, OutboxEvent
from housekeeping.services import (
    HousekeepingError,
    cancel_booking_housekeeping_tasks,
    ensure_booking_housekeeping_tasks,
    reschedule_booking_housekeeping_tasks,
)
from organizations.models import Branch, Room
from room_operations.selectors import find_room_stop_sell_conflict

from .selectors import can_create_booking_for_branch
from .special_requests import (
    SpecialRequestValidationError,
    booking_special_request_items,
    canonical_special_request_items,
    normalize_special_request_items,
    replace_booking_special_requests,
    serialize_booking_special_requests,
    special_request_summary,
)


class BookingOperationError(Exception):
    pass


class BookingCreationError(BookingOperationError):
    pass


def _booking_snapshot(booking):
    return {
        "bookingId": str(booking.id),
        "bookingCode": booking.code,
        "branchId": str(booking.branch_id),
        "roomId": str(booking.room_id),
        "status": booking.status,
        "checkinAt": booking.checkin_at.isoformat() if booking.checkin_at else None,
        "checkoutAt": booking.checkout_at.isoformat() if booking.checkout_at else None,
        "guestName": booking.guest_name,
        "guestPhone": booking.guest_phone,
        "guestCount": booking.guest_count,
        "specialRequests": booking.special_requests,
        "specialRequestItems": serialize_booking_special_requests(booking),
        "version": booking.version,
    }


def _request_items_from_cleaned_data(cleaned_data):
    raw_items = cleaned_data.get("special_request_items")
    legacy_text = "" if "special_request_items" in cleaned_data else cleaned_data.get("special_requests")
    return normalize_special_request_items(raw_items, legacy_text=legacy_text)


def _current_request_items(booking):
    return normalize_special_request_items(
        [
            {
                "request_type": item.request_type,
                "applies_to": item.applies_to,
                "priority": item.priority,
                "description": item.description,
                "quantity": item.quantity,
            }
            for item in booking_special_request_items(booking)
        ]
    )


def _record_booking_change(booking, actor, action, context, *, before=None, reason=""):
    BookingChangeLog.objects.create(
        booking=booking,
        branch=booking.branch,
        action=action,
        booking_version=booking.version,
        changed_by=actor,
        reason=str(reason or ""),
        before_snapshot=before or {},
        after_snapshot=_booking_snapshot(booking),
        correlation_id=str((context or {}).get("correlation_id") or "")[:64],
    )


def _validated_version(booking, requested_version):
    try:
        version = int(requested_version)
    except (TypeError, ValueError):
        raise BookingOperationError("Thiếu hoặc sai phiên bản booking.") from None
    if booking.version != version:
        raise BookingOperationError(
            "Booking đã được người khác cập nhật. Vui lòng tải lại dữ liệu."
        )


def _validate_booking_schedule(*, room, checkin_at, checkout_at, exclude_booking=None):
    if room.is_locked or room.status == Room.Status.OUT_OF_SERVICE:
        raise BookingOperationError("Phòng đang bị khóa hoặc ngừng phục vụ, không thể nhận booking.")
    if not checkin_at or not checkout_at:
        raise BookingOperationError("Vui lòng nhập đủ thời gian nhận và trả phòng.")
    if checkin_at < timezone.now() - timedelta(minutes=5):
        raise BookingOperationError("Thời gian nhận phòng không được ở trong quá khứ.")
    if checkout_at <= checkin_at:
        raise BookingOperationError("Thời gian trả phòng phải sau thời gian nhận phòng.")
    schedule_changed = bool(
        exclude_booking is None
        or exclude_booking.room_id != room.id
        or exclude_booking.checkin_at != checkin_at
        or exclude_booking.checkout_at != checkout_at
    )
    if schedule_changed:
        stop_sell = find_room_stop_sell_conflict(room, checkin_at, checkout_at)
        if stop_sell is not None:
            starts_local = timezone.localtime(stop_sell.starts_at)
            ends_local = timezone.localtime(stop_sell.planned_end_at)
            raise BookingOperationError(
                "Phòng đang dừng bán trong khoảng thời gian này"
                f" ({starts_local:%d/%m/%Y %H:%M} – {ends_local:%d/%m/%Y %H:%M})."
            )
    overlapping = Booking.objects.filter(
        room=room,
        checkin_at__lt=checkout_at,
        checkout_at__gt=checkin_at,
    ).exclude(status=Booking.Status.CANCELLED)
    if exclude_booking is not None:
        overlapping = overlapping.exclude(pk=exclude_booking.pk)
    if overlapping.exists():
        raise BookingOperationError("Phòng đã có booking trùng khoảng thời gian này.")


def _booking_code(branch, requested_code=""):
    requested_code = str(requested_code or "").strip().upper()[:50]
    if requested_code:
        if Booking.objects.filter(branch=branch, code__iexact=requested_code).exists():
            raise BookingCreationError("Mã booking đã tồn tại tại chi nhánh này.")
        return requested_code
    while True:
        candidate = f"BK-{timezone.localdate():%y%m%d}-{uuid.uuid4().hex[:8].upper()}"
        if not Booking.objects.filter(branch=branch, code=candidate).exists():
            return candidate


@transaction.atomic
def create_booking(actor, cleaned_data, context=None):
    context = context or {}
    try:
        branch = Branch.objects.select_for_update().get(
            pk=cleaned_data["branch"].pk,
            is_active=True,
        )
    except (Branch.DoesNotExist, KeyError, AttributeError):
        raise BookingCreationError("Chi nhánh không hợp lệ hoặc đã ngừng hoạt động.") from None
    if not can_create_booking_for_branch(actor, branch):
        raise BookingCreationError("Bạn không có quyền tạo booking tại chi nhánh này.")

    try:
        room = (
            Room.objects.select_for_update(of=("self",))
            .select_related("area_ref")
            .get(pk=cleaned_data["room"].pk, branch=branch)
        )
    except (Room.DoesNotExist, KeyError, AttributeError):
        raise BookingCreationError("Phòng không thuộc chi nhánh đã chọn.") from None
    checkin_at = cleaned_data.get("checkin_at")
    checkout_at = cleaned_data.get("checkout_at")
    try:
        _validate_booking_schedule(
            room=room,
            checkin_at=checkin_at,
            checkout_at=checkout_at,
        )
    except BookingOperationError as error:
        raise BookingCreationError(str(error)) from error
    try:
        request_items = _request_items_from_cleaned_data(cleaned_data)
    except SpecialRequestValidationError as error:
        raise BookingCreationError(str(error)) from error

    booking = Booking.objects.create(
        branch=branch,
        room=room,
        code=_booking_code(branch, cleaned_data.get("code")),
        status=Booking.Status.BOOKED,
        checkin_at=checkin_at,
        checkout_at=checkout_at,
        guest_name=str(cleaned_data.get("guest_name") or "").strip(),
        guest_phone=str(cleaned_data.get("guest_phone") or "").strip(),
        guest_count=cleaned_data.get("guest_count") or 1,
        special_requests=special_request_summary(request_items),
        source=Booking.Source.MANUAL_SALES,
        created_by=actor,
    )
    replace_booking_special_requests(booking, request_items, actor)
    tasks = ensure_booking_housekeeping_tasks(actor, booking, context)
    _record_booking_change(
        booking,
        actor,
        BookingChangeLog.Action.CREATED,
        context,
    )
    OutboxEvent.objects.get_or_create(
        deduplication_key=f"booking:{booking.id}:created"[:120],
        defaults={
            "event_type": "BOOKING_CREATED",
            "aggregate_type": "BOOKING",
            "aggregate_id": str(booking.id),
            "payload": {
                "bookingId": str(booking.id),
                "bookingCode": booking.code,
                "branchId": str(booking.branch_id),
                "roomId": str(booking.room_id),
                "checkinAt": booking.checkin_at.isoformat(),
                "checkoutAt": booking.checkout_at.isoformat(),
                "specialRequestItems": serialize_booking_special_requests(booking),
                "createdById": str(actor.id),
                "taskIds": [str(task.id) for task in tasks],
            },
        },
    )
    return booking, tasks


@transaction.atomic
def update_booking(actor, booking_id, cleaned_data, requested_version, context=None):
    context = context or {}
    try:
        booking = (
            Booking.objects.select_for_update(of=("self",))
            .select_related("branch", "room", "room__area_ref")
            .get(pk=booking_id)
        )
    except (Booking.DoesNotExist, ValueError):
        raise BookingOperationError("Không tìm thấy booking.") from None
    if not can_create_booking_for_branch(actor, booking.branch):
        raise BookingOperationError("Bạn không có quyền cập nhật booking tại chi nhánh này.")
    if booking.status != Booking.Status.BOOKED:
        raise BookingOperationError("Chỉ booking đang ở trạng thái Đã đặt mới được chỉnh sửa.")

    try:
        room_id = cleaned_data["room"].pk
    except (KeyError, AttributeError):
        raise BookingOperationError("Phòng không hợp lệ.") from None
    room_ids = sorted({booking.room_id, room_id}, key=str)
    locked_rooms = {
        room.id: room
        for room in Room.objects.select_for_update(of=("self",))
        .select_related("area_ref")
        .filter(pk__in=room_ids, branch=booking.branch)
        .order_by("id")
    }
    try:
        room = locked_rooms[room_id]
    except KeyError:
        raise BookingOperationError("Phòng không thuộc chi nhánh của booking.") from None
    try:
        request_items = _request_items_from_cleaned_data(cleaned_data)
    except SpecialRequestValidationError as error:
        raise BookingOperationError(str(error)) from error

    values = {
        "room": room,
        "guest_name": str(cleaned_data.get("guest_name") or "").strip(),
        "guest_phone": str(cleaned_data.get("guest_phone") or "").strip(),
        "guest_count": cleaned_data.get("guest_count") or 1,
        "checkin_at": cleaned_data.get("checkin_at"),
        "checkout_at": cleaned_data.get("checkout_at"),
        "special_requests": special_request_summary(request_items),
    }
    desired_matches_current = all(
        getattr(booking, field) == value
        for field, value in values.items()
    ) and canonical_special_request_items(_current_request_items(booking)) == canonical_special_request_items(
        request_items
    )
    if desired_matches_current:
        return booking, list(booking.housekeeping_tasks.order_by("task_type", "id"))
    _validated_version(booking, requested_version)
    _validate_booking_schedule(
        room=room,
        checkin_at=values["checkin_at"],
        checkout_at=values["checkout_at"],
        exclude_booking=booking,
    )

    before = _booking_snapshot(booking)
    previous_room = booking.room
    for field, value in values.items():
        setattr(booking, field, value)
    booking.updated_by = actor
    booking.version += 1
    booking.save(
        update_fields=[
            *values.keys(),
            "updated_by",
            "version",
            "updated_at",
        ]
    )
    replace_booking_special_requests(booking, request_items, actor)
    try:
        tasks = reschedule_booking_housekeeping_tasks(
            actor,
            booking,
            context,
            previous_room=previous_room,
        )
    except HousekeepingError as error:
        raise BookingOperationError(error.message) from error
    _record_booking_change(
        booking,
        actor,
        BookingChangeLog.Action.CHANGED,
        context,
        before=before,
    )
    OutboxEvent.objects.get_or_create(
        deduplication_key=f"booking:{booking.id}:changed:v{booking.version}"[:120],
        defaults={
            "event_type": "BOOKING_CHANGED",
            "aggregate_type": "BOOKING",
            "aggregate_id": str(booking.id),
            "payload": {
                "before": before,
                "after": _booking_snapshot(booking),
                "changedById": str(actor.id),
                "taskIds": [str(task.id) for task in tasks],
            },
        },
    )
    return booking, tasks


@transaction.atomic
def cancel_booking(actor, booking_id, requested_version, reason, context=None):
    context = context or {}
    reason = str(reason or "").strip()
    if not reason:
        raise BookingOperationError("Hủy booking phải có lý do.")
    try:
        booking = (
            Booking.objects.select_for_update(of=("self",))
            .select_related("branch", "room")
            .get(pk=booking_id)
        )
    except (Booking.DoesNotExist, ValueError):
        raise BookingOperationError("Không tìm thấy booking.") from None
    if not can_create_booking_for_branch(actor, booking.branch):
        raise BookingOperationError("Bạn không có quyền hủy booking tại chi nhánh này.")
    if booking.status == Booking.Status.CANCELLED:
        return booking, list(booking.housekeeping_tasks.order_by("task_type", "id"))
    if booking.status != Booking.Status.BOOKED:
        raise BookingOperationError("Chỉ booking đang ở trạng thái Đã đặt mới được hủy.")
    _validated_version(booking, requested_version)

    before = _booking_snapshot(booking)
    booking.status = Booking.Status.CANCELLED
    booking.cancelled_at = timezone.now()
    booking.cancelled_by = actor
    booking.cancellation_reason = reason
    booking.updated_by = actor
    booking.version += 1
    booking.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancelled_by",
            "cancellation_reason",
            "updated_by",
            "version",
            "updated_at",
        ]
    )
    try:
        tasks = cancel_booking_housekeeping_tasks(actor, booking, reason, context)
    except HousekeepingError as error:
        raise BookingOperationError(error.message) from error
    _record_booking_change(
        booking,
        actor,
        BookingChangeLog.Action.CANCELLED,
        context,
        before=before,
        reason=reason,
    )
    OutboxEvent.objects.get_or_create(
        deduplication_key=f"booking:{booking.id}:cancelled:v{booking.version}"[:120],
        defaults={
            "event_type": "BOOKING_CANCELLED",
            "aggregate_type": "BOOKING",
            "aggregate_id": str(booking.id),
            "payload": {
                "before": before,
                "after": _booking_snapshot(booking),
                "cancelledById": str(actor.id),
                "reason": reason,
                "taskIds": [str(task.id) for task in tasks],
            },
        },
    )
    return booking, tasks
