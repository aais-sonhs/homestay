from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from housekeeping.models import Booking, IssueTicket, OutboxEvent
from organizations.models import Branch, Room

from .models import (
    RoomBlocker,
    RoomBlockerHistory,
    RoomStopSell,
    RoomStopSellHistory,
)
from .selectors import (
    OPEN_STOP_SELL_STATUSES,
    can_manage_room_sales_status,
)


class RoomOperationsError(Exception):
    def __init__(self, code, message, *, status=400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def _correlation_id(context):
    return str((context or {}).get("correlation_id") or "")[:64]


def _blocker_snapshot(blocker):
    return {
        "blockerId": str(blocker.id),
        "branchId": str(blocker.branch_id),
        "roomId": str(blocker.room_id),
        "issueId": str(blocker.issue_id) if blocker.issue_id else None,
        "kind": blocker.kind,
        "status": blocker.status,
        "reason": blocker.reason,
        "startsAt": blocker.starts_at.isoformat() if blocker.starts_at else None,
        "plannedEndAt": blocker.planned_end_at.isoformat() if blocker.planned_end_at else None,
        "version": blocker.version,
    }


def _stop_sell_snapshot(stop_sell):
    return {
        "stopSellId": str(stop_sell.id),
        "blockerId": str(stop_sell.blocker_id),
        "branchId": str(stop_sell.branch_id),
        "roomId": str(stop_sell.room_id),
        "reasonCode": stop_sell.reason_code,
        "reason": stop_sell.reason,
        "startsAt": stop_sell.starts_at.isoformat(),
        "plannedEndAt": stop_sell.planned_end_at.isoformat(),
        "status": stop_sell.status,
        "reopenedAt": stop_sell.reopened_at.isoformat() if stop_sell.reopened_at else None,
        "version": stop_sell.version,
    }


def _record_blocker_history(blocker, actor, action, context, *, before=None, note=""):
    RoomBlockerHistory.objects.create(
        blocker=blocker,
        branch=blocker.branch,
        action=action,
        blocker_version=blocker.version,
        actor=actor,
        note=str(note or ""),
        before_snapshot=before or {},
        after_snapshot=_blocker_snapshot(blocker),
        correlation_id=_correlation_id(context),
    )


def _record_stop_sell_history(stop_sell, actor, action, context, *, before=None, note=""):
    RoomStopSellHistory.objects.create(
        stop_sell=stop_sell,
        branch=stop_sell.branch,
        action=action,
        stop_sell_version=stop_sell.version,
        actor=actor,
        note=str(note or ""),
        before_snapshot=before or {},
        after_snapshot=_stop_sell_snapshot(stop_sell),
        correlation_id=_correlation_id(context),
    )


def _outbox(event_type, aggregate_type, aggregate_id, version, payload):
    return OutboxEvent.objects.get_or_create(
        deduplication_key=f"{aggregate_type.lower()}:{aggregate_id}:{event_type.lower()}:v{version}"[:120],
        defaults={
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": str(aggregate_id),
            "payload": payload,
        },
    )[0]


def _ensure_manage(actor, branch):
    if not can_manage_room_sales_status(actor, branch):
        raise RoomOperationsError(
            "ROOM_STOP_SELL_ACCESS_DENIED",
            "Bạn không có quyền thay đổi khả năng bán tại chi nhánh này.",
            status=403,
        )


def _check_version(instance, requested_version, label):
    try:
        requested_version = int(requested_version)
    except (TypeError, ValueError):
        raise RoomOperationsError("STALE_VERSION", f"Thiếu hoặc sai phiên bản {label}.") from None
    if instance.version != requested_version:
        raise RoomOperationsError(
            "STALE_VERSION",
            f"{label} đã được người khác cập nhật. Vui lòng tải lại dữ liệu.",
            status=409,
        )


@transaction.atomic
def ensure_issue_blocker(issue, actor, context=None):
    if not issue.blocks_room_ready:
        return None, False
    existing = RoomBlocker.objects.select_for_update().filter(issue=issue).first()
    if existing:
        return existing, False
    blocker = RoomBlocker.objects.create(
        branch=issue.task.branch,
        room=issue.room,
        issue=issue,
        kind=RoomBlocker.Kind.ISSUE,
        status=RoomBlocker.Status.ACTIVE,
        reason=issue.description[:500],
        starts_at=issue.created_at or timezone.now(),
        created_by=actor,
    )
    _record_blocker_history(
        blocker,
        actor,
        RoomBlockerHistory.Action.CREATED,
        context,
        note=issue.description,
    )
    snapshot = _blocker_snapshot(blocker)
    _outbox("ROOM_BLOCKER_CREATED", "ROOM_BLOCKER", blocker.id, blocker.version, snapshot)
    _outbox("ROOM_READINESS_CHANGED", "ROOM", blocker.id, blocker.version, snapshot)
    return blocker, True


@transaction.atomic
def request_issue_blocker_clearance(issue, actor, note, context=None):
    blocker = RoomBlocker.objects.select_for_update().filter(issue=issue).first()
    if blocker is None:
        return None, False
    if issue.status not in {IssueTicket.Status.RESOLVED, IssueTicket.Status.CANCELLED}:
        raise RoomOperationsError(
            "BLOCKER_SOURCE_OPEN",
            "Sự cố nguồn chưa được xử lý xong.",
            status=409,
        )
    if blocker.status == RoomBlocker.Status.CLEARANCE_PENDING:
        return blocker, False
    if blocker.status in {RoomBlocker.Status.CLEARED, RoomBlocker.Status.CANCELLED}:
        return blocker, False
    before = _blocker_snapshot(blocker)
    blocker.status = RoomBlocker.Status.CLEARANCE_PENDING
    blocker.clearance_requested_by = actor
    blocker.clearance_requested_at = timezone.now()
    blocker.clearance_note = str(note or issue.resolution_note or "")
    blocker.version += 1
    blocker.save(
        update_fields=[
            "status",
            "clearance_requested_by",
            "clearance_requested_at",
            "clearance_note",
            "version",
            "updated_at",
        ]
    )
    _record_blocker_history(
        blocker,
        actor,
        RoomBlockerHistory.Action.CLEARANCE_REQUESTED,
        context,
        before=before,
        note=blocker.clearance_note,
    )
    _outbox(
        "ROOM_BLOCKER_CLEARANCE_REQUESTED",
        "ROOM_BLOCKER",
        blocker.id,
        blocker.version,
        _blocker_snapshot(blocker),
    )
    return blocker, True


def _validate_source_ready_for_clearance(blocker):
    if blocker.issue_id and blocker.issue.status not in {
        IssueTicket.Status.RESOLVED,
        IssueTicket.Status.CANCELLED,
    }:
        raise RoomOperationsError(
            "BLOCKER_SOURCE_OPEN",
            "Sự cố nguồn chưa được xử lý xong nên chưa thể gỡ blocker.",
            status=409,
        )


def _clear_blocker(blocker, actor, note, context):
    before = _blocker_snapshot(blocker)
    blocker.status = RoomBlocker.Status.CLEARED
    blocker.cleared_by = actor
    blocker.cleared_at = timezone.now()
    blocker.resolution_note = note
    blocker.version += 1
    blocker.save(
        update_fields=[
            "status",
            "cleared_by",
            "cleared_at",
            "resolution_note",
            "version",
            "updated_at",
        ]
    )
    _record_blocker_history(
        blocker,
        actor,
        RoomBlockerHistory.Action.CLEARED,
        context,
        before=before,
        note=note,
    )
    snapshot = _blocker_snapshot(blocker)
    _outbox("ROOM_BLOCKER_CLEARED", "ROOM_BLOCKER", blocker.id, blocker.version, snapshot)
    _outbox("ROOM_READINESS_CHANGED", "ROOM", blocker.id, blocker.version, snapshot)
    return blocker


@transaction.atomic
def confirm_room_blocker_clearance(actor, blocker_id, requested_version, note, context=None):
    note = str(note or "").strip()
    if not note:
        raise RoomOperationsError("BLOCKER_NOTE_REQUIRED", "Xác nhận gỡ blocker phải có ghi chú.")
    try:
        blocker = (
            RoomBlocker.objects.select_for_update(of=("self",))
            .select_related("branch", "room", "issue")
            .get(pk=blocker_id)
        )
    except (RoomBlocker.DoesNotExist, ValueError):
        raise RoomOperationsError("BLOCKER_NOT_FOUND", "Không tìm thấy blocker.", status=404) from None
    _ensure_manage(actor, blocker.branch)
    _check_version(blocker, requested_version, "blocker")
    if blocker.status != RoomBlocker.Status.CLEARANCE_PENDING:
        raise RoomOperationsError(
            "BLOCKER_INVALID_STATUS",
            "Blocker chưa ở trạng thái chờ xác nhận gỡ.",
            status=409,
        )
    _validate_source_ready_for_clearance(blocker)
    if blocker.stop_sells.filter(status__in=OPEN_STOP_SELL_STATUSES).exists():
        raise RoomOperationsError(
            "STOP_SELL_STILL_OPEN",
            "Phải xác nhận mở bán lại trước khi gỡ blocker.",
            status=409,
        )
    return _clear_blocker(blocker, actor, note, context)


@transaction.atomic
def create_room_stop_sell(actor, cleaned_data, context=None):
    try:
        branch_id = cleaned_data["branch"].pk
        room_id = cleaned_data["room"].pk
    except (KeyError, AttributeError):
        raise RoomOperationsError("STOP_SELL_INVALID_SCOPE", "Chi nhánh hoặc phòng không hợp lệ.") from None
    try:
        branch = Branch.objects.select_for_update().get(pk=branch_id, is_active=True)
        room = Room.objects.select_for_update(of=("self",)).get(pk=room_id, branch=branch)
    except (Branch.DoesNotExist, Room.DoesNotExist, ValueError):
        raise RoomOperationsError("STOP_SELL_INVALID_SCOPE", "Phòng không thuộc chi nhánh đã chọn.", status=404) from None
    _ensure_manage(actor, branch)

    starts_at = cleaned_data.get("starts_at")
    planned_end_at = cleaned_data.get("planned_end_at")
    if not starts_at or not planned_end_at or planned_end_at <= starts_at:
        raise RoomOperationsError("STOP_SELL_INVALID_RANGE", "Thời gian kết thúc phải sau thời gian bắt đầu.")
    if starts_at < timezone.now() - timedelta(minutes=5):
        raise RoomOperationsError("STOP_SELL_INVALID_RANGE", "Không thể tạo khoảng dừng bán trong quá khứ.")
    existing_open = list(
        RoomStopSell.objects.select_for_update()
        .filter(room=room, status__in=OPEN_STOP_SELL_STATUSES)
        .order_by("starts_at", "created_at")
    )
    if existing_open:
        raise RoomOperationsError(
            "STOP_SELL_OVERLAP",
            "Phòng đã có lịch dừng bán đang mở hoặc đang chờ xác nhận mở lại.",
            status=409,
        )

    source_blocker = cleaned_data.get("blocker")
    blocker_created = False
    if source_blocker:
        try:
            blocker = (
                RoomBlocker.objects.select_for_update(of=("self",))
                .select_related("issue")
                .get(
                    pk=source_blocker.pk,
                    branch=branch,
                    room=room,
                    status=RoomBlocker.Status.ACTIVE,
                )
            )
        except (RoomBlocker.DoesNotExist, ValueError):
            raise RoomOperationsError(
                "BLOCKER_NOT_FOUND",
                "Blocker nguồn không hợp lệ hoặc không còn hoạt động.",
                status=404,
            ) from None
        if blocker.stop_sells.filter(status__in=OPEN_STOP_SELL_STATUSES).exists():
            raise RoomOperationsError(
                "STOP_SELL_OVERLAP",
                "Blocker này đã có khoảng dừng bán đang mở.",
                status=409,
            )
    else:
        blocker = RoomBlocker.objects.create(
            branch=branch,
            room=room,
            kind=RoomBlocker.Kind.MANUAL,
            status=RoomBlocker.Status.ACTIVE,
            reason=str(cleaned_data.get("reason") or "").strip()[:500],
            starts_at=starts_at,
            planned_end_at=planned_end_at,
            created_by=actor,
        )
        blocker_created = True
        _record_blocker_history(
            blocker,
            actor,
            RoomBlockerHistory.Action.CREATED,
            context,
            note=blocker.reason,
        )
        _outbox(
            "ROOM_BLOCKER_CREATED",
            "ROOM_BLOCKER",
            blocker.id,
            blocker.version,
            _blocker_snapshot(blocker),
        )

    reason = str(cleaned_data.get("reason") or "").strip()
    reason_code = str(cleaned_data.get("reason_code") or "")
    if not reason or reason_code not in RoomStopSell.ReasonCode.values:
        raise RoomOperationsError("STOP_SELL_REASON_REQUIRED", "Vui lòng chọn và nhập lý do dừng bán.")
    stop_sell = RoomStopSell.objects.create(
        branch=branch,
        room=room,
        blocker=blocker,
        reason_code=reason_code,
        reason=reason[:500],
        starts_at=starts_at,
        planned_end_at=planned_end_at,
        status=RoomStopSell.Status.ACTIVE,
        created_by=actor,
    )
    _record_stop_sell_history(
        stop_sell,
        actor,
        RoomStopSellHistory.Action.CREATED,
        context,
        note=reason,
    )
    affected_booking_count = Booking.objects.filter(
        room=room,
        checkin_at__lt=planned_end_at,
        checkout_at__gt=starts_at,
    ).exclude(status=Booking.Status.CANCELLED).count()
    payload = {
        **_stop_sell_snapshot(stop_sell),
        "blockerCreated": blocker_created,
        "affectedBookingCount": affected_booking_count,
        "createdById": str(actor.id),
    }
    _outbox("ROOM_STOP_SELL_STARTED", "ROOM_STOP_SELL", stop_sell.id, stop_sell.version, payload)
    _outbox("ROOM_READINESS_CHANGED", "ROOM", stop_sell.id, stop_sell.version, payload)
    return stop_sell, affected_booking_count


def _get_stop_sell_for_update(stop_sell_id):
    try:
        return (
            RoomStopSell.objects.select_for_update(of=("self",))
            .select_related("branch", "room", "blocker", "blocker__issue")
            .get(pk=stop_sell_id)
        )
    except (RoomStopSell.DoesNotExist, ValueError):
        raise RoomOperationsError("STOP_SELL_NOT_FOUND", "Không tìm thấy khoảng dừng bán.", status=404) from None


@transaction.atomic
def request_room_reopen(actor, stop_sell_id, requested_version, note, context=None):
    note = str(note or "").strip()
    if not note:
        raise RoomOperationsError("STOP_SELL_NOTE_REQUIRED", "Yêu cầu mở lại phải có ghi chú kết quả xử lý.")
    stop_sell = _get_stop_sell_for_update(stop_sell_id)
    _ensure_manage(actor, stop_sell.branch)
    _check_version(stop_sell, requested_version, "khoảng dừng bán")
    if stop_sell.status != RoomStopSell.Status.ACTIVE:
        raise RoomOperationsError("STOP_SELL_INVALID_STATUS", "Khoảng dừng bán không thể yêu cầu mở lại.", status=409)
    if stop_sell.starts_at > timezone.now():
        raise RoomOperationsError(
            "STOP_SELL_NOT_STARTED",
            "Lịch dừng bán chưa bắt đầu; hãy hủy lịch nếu không còn cần thiết.",
            status=409,
        )
    _validate_source_ready_for_clearance(stop_sell.blocker)

    before = _stop_sell_snapshot(stop_sell)
    now = timezone.now()
    stop_sell.status = RoomStopSell.Status.REOPEN_REQUESTED
    stop_sell.reopen_requested_by = actor
    stop_sell.reopen_requested_at = now
    stop_sell.reopen_request_note = note
    stop_sell.version += 1
    stop_sell.save(
        update_fields=[
            "status",
            "reopen_requested_by",
            "reopen_requested_at",
            "reopen_request_note",
            "version",
            "updated_at",
        ]
    )
    blocker = stop_sell.blocker
    if blocker.status == RoomBlocker.Status.ACTIVE:
        blocker_before = _blocker_snapshot(blocker)
        blocker.status = RoomBlocker.Status.CLEARANCE_PENDING
        blocker.clearance_requested_by = actor
        blocker.clearance_requested_at = now
        blocker.clearance_note = note
        blocker.version += 1
        blocker.save(
            update_fields=[
                "status",
                "clearance_requested_by",
                "clearance_requested_at",
                "clearance_note",
                "version",
                "updated_at",
            ]
        )
        _record_blocker_history(
            blocker,
            actor,
            RoomBlockerHistory.Action.CLEARANCE_REQUESTED,
            context,
            before=blocker_before,
            note=note,
        )
    _record_stop_sell_history(
        stop_sell,
        actor,
        RoomStopSellHistory.Action.REOPEN_REQUESTED,
        context,
        before=before,
        note=note,
    )
    _outbox(
        "ROOM_STOP_SELL_REOPEN_REQUESTED",
        "ROOM_STOP_SELL",
        stop_sell.id,
        stop_sell.version,
        _stop_sell_snapshot(stop_sell),
    )
    return stop_sell


@transaction.atomic
def confirm_room_reopen(actor, stop_sell_id, requested_version, note, context=None):
    note = str(note or "").strip()
    if not note:
        raise RoomOperationsError("STOP_SELL_NOTE_REQUIRED", "Xác nhận mở lại phải có ghi chú.")
    stop_sell = _get_stop_sell_for_update(stop_sell_id)
    _ensure_manage(actor, stop_sell.branch)
    _check_version(stop_sell, requested_version, "khoảng dừng bán")
    if stop_sell.status != RoomStopSell.Status.REOPEN_REQUESTED:
        raise RoomOperationsError(
            "STOP_SELL_INVALID_STATUS",
            "Khoảng dừng bán chưa có yêu cầu mở lại để xác nhận.",
            status=409,
        )
    blocker = (
        RoomBlocker.objects.select_for_update(of=("self",))
        .select_related("issue")
        .get(pk=stop_sell.blocker_id)
    )
    _validate_source_ready_for_clearance(blocker)
    before = _stop_sell_snapshot(stop_sell)
    now = timezone.now()
    stop_sell.status = RoomStopSell.Status.ENDED
    stop_sell.reopened_by = actor
    stop_sell.reopened_at = now
    stop_sell.reopen_confirmation_note = note
    stop_sell.version += 1
    stop_sell.save(
        update_fields=[
            "status",
            "reopened_by",
            "reopened_at",
            "reopen_confirmation_note",
            "version",
            "updated_at",
        ]
    )
    _record_stop_sell_history(
        stop_sell,
        actor,
        RoomStopSellHistory.Action.REOPEN_CONFIRMED,
        context,
        before=before,
        note=note,
    )
    if not blocker.stop_sells.exclude(pk=stop_sell.pk).filter(status__in=OPEN_STOP_SELL_STATUSES).exists():
        _clear_blocker(blocker, actor, note, context)
    payload = {**_stop_sell_snapshot(stop_sell), "reopenedById": str(actor.id)}
    _outbox("ROOM_STOP_SELL_ENDED", "ROOM_STOP_SELL", stop_sell.id, stop_sell.version, payload)
    _outbox("ROOM_READINESS_CHANGED", "ROOM", stop_sell.id, stop_sell.version, payload)
    return stop_sell


@transaction.atomic
def cancel_scheduled_stop_sell(actor, stop_sell_id, requested_version, note, context=None):
    note = str(note or "").strip()
    if not note:
        raise RoomOperationsError("STOP_SELL_NOTE_REQUIRED", "Hủy lịch dừng bán phải có lý do.")
    stop_sell = _get_stop_sell_for_update(stop_sell_id)
    _ensure_manage(actor, stop_sell.branch)
    _check_version(stop_sell, requested_version, "khoảng dừng bán")
    if stop_sell.status != RoomStopSell.Status.ACTIVE or stop_sell.starts_at <= timezone.now():
        raise RoomOperationsError(
            "STOP_SELL_INVALID_STATUS",
            "Chỉ lịch dừng bán chưa bắt đầu mới được hủy.",
            status=409,
        )
    before = _stop_sell_snapshot(stop_sell)
    stop_sell.status = RoomStopSell.Status.CANCELLED
    stop_sell.cancelled_by = actor
    stop_sell.cancelled_at = timezone.now()
    stop_sell.cancellation_reason = note
    stop_sell.version += 1
    stop_sell.save(
        update_fields=[
            "status",
            "cancelled_by",
            "cancelled_at",
            "cancellation_reason",
            "version",
            "updated_at",
        ]
    )
    _record_stop_sell_history(
        stop_sell,
        actor,
        RoomStopSellHistory.Action.CANCELLED,
        context,
        before=before,
        note=note,
    )
    blocker = RoomBlocker.objects.select_for_update().get(pk=stop_sell.blocker_id)
    if (
        blocker.kind == RoomBlocker.Kind.MANUAL
        and blocker.issue_id is None
        and not blocker.stop_sells.exclude(pk=stop_sell.pk).filter(status__in=OPEN_STOP_SELL_STATUSES).exists()
    ):
        blocker_before = _blocker_snapshot(blocker)
        blocker.status = RoomBlocker.Status.CANCELLED
        blocker.version += 1
        blocker.save(update_fields=["status", "version", "updated_at"])
        _record_blocker_history(
            blocker,
            actor,
            RoomBlockerHistory.Action.CANCELLED,
            context,
            before=blocker_before,
            note=note,
        )
    _outbox(
        "ROOM_STOP_SELL_CANCELLED",
        "ROOM_STOP_SELL",
        stop_sell.id,
        stop_sell.version,
        _stop_sell_snapshot(stop_sell),
    )
    return stop_sell
