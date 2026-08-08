from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Prefetch, Q
from django.utils import timezone

from common.access import (
    GLOBAL_ROLES,
    active_memberships,
    can_view_booking_guest,
    is_active_user,
    is_branch_owner,
)
from housekeeping.models import Booking, HousekeepingTask, IssueTicket, TaskPhoto
from organizations.models import Branch, BranchMembership, Room
from organizations.selectors import branch_queryset_for_user, room_queryset_for_user

from .models import RoomBlocker, RoomStopSell


TERMINAL_TASK_STATUSES = {
    HousekeepingTask.Status.QC_APPROVED,
    HousekeepingTask.Status.CANCELLED,
}
TERMINAL_ISSUE_STATUSES = {
    IssueTicket.Status.RESOLVED,
    IssueTicket.Status.CANCELLED,
}
OPEN_BLOCKER_STATUSES = {
    RoomBlocker.Status.ACTIVE,
    RoomBlocker.Status.CLEARANCE_PENDING,
}
OPEN_STOP_SELL_STATUSES = {
    RoomStopSell.Status.ACTIVE,
    RoomStopSell.Status.REOPEN_REQUESTED,
}


def can_manage_room_sales_status(user, branch):
    if not is_active_user(user) or not branch.is_active:
        return False
    if user.role in GLOBAL_ROLES or is_branch_owner(user, branch):
        return True
    return active_memberships(user).filter(
        branch=branch,
        membership_role=BranchMembership.MembershipRole.MANAGER,
    ).exists()


def room_sales_management_branch_queryset(user):
    queryset = Branch.objects.filter(is_active=True)
    if not is_active_user(user):
        return queryset.none()
    if user.role in GLOBAL_ROLES:
        return queryset.order_by("name", "code")
    manager_memberships = active_memberships(user).filter(
        membership_role=BranchMembership.MembershipRole.MANAGER,
    )
    return (
        queryset.filter(Q(owner=user) | Q(memberships__in=manager_memberships))
        .distinct()
        .order_by("name", "code")
    )


def can_manage_any_room_sales_status(user):
    return room_sales_management_branch_queryset(user).exists()


def stop_sell_queryset_for_user(user):
    allowed_rooms = room_queryset_for_user(user)
    return (
        RoomStopSell.objects.filter(room__in=allowed_rooms)
        .select_related(
            "branch",
            "room",
            "blocker",
            "blocker__issue",
            "created_by",
            "reopen_requested_by",
            "reopened_by",
        )
        .prefetch_related("history")
    )


def blocker_queryset_for_user(user):
    return (
        RoomBlocker.objects.filter(room__in=room_queryset_for_user(user))
        .select_related("branch", "room", "issue", "created_by")
        .prefetch_related("stop_sells")
    )


def stop_sell_effective_end(stop_sell, *, at=None):
    if stop_sell.status == RoomStopSell.Status.ENDED:
        return stop_sell.reopened_at
    if stop_sell.status == RoomStopSell.Status.CANCELLED:
        return stop_sell.starts_at
    # Planned end is an ETA, not permission to reopen. An open stop-sell remains
    # effective until the explicit confirmation transition records reopened_at.
    return None


def stop_sell_overlaps(stop_sell, starts_at, ends_at, *, at=None):
    if not starts_at or not ends_at or stop_sell.status not in OPEN_STOP_SELL_STATUSES:
        return False
    effective_end = stop_sell_effective_end(stop_sell, at=at)
    return bool(
        stop_sell.starts_at < ends_at
        and (effective_end is None or effective_end > starts_at)
    )


def find_room_stop_sell_conflict(room, starts_at, ends_at, *, at=None):
    if not starts_at or not ends_at:
        return None
    queryset = RoomStopSell.objects.filter(
        room=room,
        status__in=OPEN_STOP_SELL_STATUSES,
        starts_at__lt=ends_at,
    ).order_by("starts_at", "created_at")
    return next(
        (
            stop_sell
            for stop_sell in queryset
            if stop_sell_overlaps(stop_sell, starts_at, ends_at, at=at)
        ),
        None,
    )


def _active_tasks_queryset(at):
    immediately_blocking_statuses = {
        HousekeepingTask.Status.IN_PROGRESS,
        HousekeepingTask.Status.PAUSED,
        HousekeepingTask.Status.WAITING_SUPPORT,
        HousekeepingTask.Status.COMPLETED,
        HousekeepingTask.Status.WAITING_QC,
        HousekeepingTask.Status.QC_REJECTED,
    }
    return (
        HousekeepingTask.objects.exclude(status__in=TERMINAL_TASK_STATUSES)
        .filter(
            Q(status__in=immediately_blocking_statuses)
            | Q(scheduled_start_at__lte=at + timedelta(hours=24))
        )
        .select_related("assignee", "booking", "shift")
        .order_by("due_at", "code")
    )


def _blocking_issues_queryset():
    return (
        IssueTicket.objects.filter(blocks_room_ready=True)
        .exclude(status__in=TERMINAL_ISSUE_STATUSES)
        .select_related("assigned_to", "task")
        .order_by("-created_at")
    )


def _upcoming_bookings_queryset(at):
    return (
        Booking.objects.exclude(status=Booking.Status.CANCELLED)
        .filter(Q(checkout_at__gte=at) | Q(checkout_at__isnull=True))
        .order_by("checkin_at", "code")
    )


def _open_blockers_queryset():
    return (
        RoomBlocker.objects.filter(status__in=OPEN_BLOCKER_STATUSES)
        .select_related("issue", "created_by", "clearance_requested_by")
        .order_by("starts_at", "created_at")
    )


def _open_stop_sells_queryset():
    return (
        RoomStopSell.objects.filter(status__in=OPEN_STOP_SELL_STATUSES)
        .select_related("blocker", "created_by", "reopen_requested_by")
        .order_by("starts_at", "created_at")
    )


def _room_readiness_row(room, at):
    active_tasks = list(getattr(room, "active_operations_tasks", []))
    blocking_issues = list(getattr(room, "active_blocking_issues", []))
    upcoming_bookings = list(getattr(room, "upcoming_operations_bookings", []))
    operational_blockers = [
        blocker
        for blocker in getattr(room, "active_operational_blockers", [])
        if blocker.starts_at <= at
    ]
    open_stop_sells = list(getattr(room, "active_room_stop_sells", []))
    active_stop_sells = [
        stop_sell
        for stop_sell in open_stop_sells
        if stop_sell.starts_at <= at
    ]
    blockers = []

    if room.status == Room.Status.OUT_OF_SERVICE:
        blockers.append({"code": "OUT_OF_SERVICE", "label": "Phòng ngừng phục vụ", "level": "danger"})
    if room.is_locked:
        blockers.append({"code": "ROOM_LOCKED", "label": "Phòng đang bị khóa", "level": "danger"})
    covered_issue_ids = {
        blocker.issue_id for blocker in operational_blockers if blocker.issue_id
    }
    uncovered_blocking_issues = [
        issue for issue in blocking_issues if issue.id not in covered_issue_ids
    ]
    for blocker in operational_blockers:
        blockers.append(
            {
                "code": f"OPERATIONAL_{blocker.kind}",
                "label": f"{blocker.get_kind_display()}: {blocker.reason}",
                "level": "danger",
                "source": blocker,
            }
        )
    if uncovered_blocking_issues:
        blockers.append(
            {
                "code": "BLOCKING_ISSUE",
                "label": f"{len(uncovered_blocking_issues)} sự cố đang chặn phòng",
                "level": "danger",
            }
        )
    if room.status not in {Room.Status.READY, Room.Status.OUT_OF_SERVICE}:
        blockers.append(
            {
                "code": "CLEANLINESS_NOT_READY",
                "label": room.get_status_display(),
                "level": "warning",
            }
        )
    if active_tasks and room.status == Room.Status.READY:
        blockers.append(
            {
                "code": "ACTIVE_TASK_EXISTS",
                "label": f"Còn {len(active_tasks)} công việc đang mở",
                "level": "warning",
            }
        )

    hard_blocked = bool(
        room.is_locked
        or room.status == Room.Status.OUT_OF_SERVICE
        or blocking_issues
        or operational_blockers
    )
    ready_for_guest = bool(
        room.status == Room.Status.READY
        and not blockers
        and not room.is_guest_occupied
    )
    if hard_blocked:
        state = "BLOCKED"
        state_label = "Đang bị chặn"
    elif room.is_guest_occupied:
        state = "OCCUPIED"
        state_label = "Đang có khách"
    elif ready_for_guest:
        state = "READY"
        state_label = "Sẵn sàng"
    else:
        state = "NOT_READY"
        state_label = "Chưa sẵn sàng"

    expected_ready_at = max(
        [task.due_at for task in active_tasks if task.due_at]
        + [blocker.planned_end_at for blocker in operational_blockers if blocker.planned_end_at]
        + [stop_sell.planned_end_at for stop_sell in active_stop_sells],
        default=None,
    )
    next_booking = upcoming_bookings[0] if upcoming_bookings else None
    next_booking_stop_sell = next(
        (
            stop_sell
            for stop_sell in open_stop_sells
            if next_booking
            and stop_sell_overlaps(
                stop_sell,
                next_booking.checkin_at,
                next_booking.checkout_at,
                at=at,
            )
        ),
        None,
    )
    checkin_risk = bool(
        next_booking
        and next_booking.checkin_at
        and next_booking.checkin_at <= at + timedelta(hours=24)
        and (state not in {"READY", "OCCUPIED"} or next_booking_stop_sell)
    )
    return {
        "room": room,
        "state": state,
        "stateLabel": state_label,
        "readyForGuest": ready_for_guest,
        "blockers": blockers,
        "activeTasks": active_tasks,
        "blockingIssues": blocking_issues,
        "operationalBlockers": operational_blockers,
        "activeStopSells": active_stop_sells,
        "openStopSells": open_stop_sells,
        "nextBookingStopSell": next_booking_stop_sell,
        "salesStatus": (
            "STOP_SELL"
            if active_stop_sells
            else ("BLOCKED" if hard_blocked else "OPEN")
        ),
        "salesStatusLabel": (
            "Dừng bán"
            if active_stop_sells
            else ("Có blocker" if hard_blocked else "Mở bán")
        ),
        "nextBooking": next_booking,
        "expectedReadyAt": expected_ready_at,
        "checkinRisk": checkin_risk,
    }


def readiness_rows_for_user(user, *, branch_id=None, query="", state="", room_id=None, at=None):
    at = at or timezone.now()
    queryset = room_queryset_for_user(user).filter(branch__is_active=True)
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    if room_id:
        queryset = queryset.filter(pk=room_id)
    query = str(query or "").strip()
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(floor__icontains=query)
            | Q(area__icontains=query)
        )
    queryset = queryset.prefetch_related(
        Prefetch("housekeeping_tasks", queryset=_active_tasks_queryset(at), to_attr="active_operations_tasks"),
        Prefetch("issues", queryset=_blocking_issues_queryset(), to_attr="active_blocking_issues"),
        Prefetch("bookings", queryset=_upcoming_bookings_queryset(at), to_attr="upcoming_operations_bookings"),
        Prefetch("operational_blockers", queryset=_open_blockers_queryset(), to_attr="active_operational_blockers"),
        Prefetch("stop_sells", queryset=_open_stop_sells_queryset(), to_attr="active_room_stop_sells"),
    ).order_by("branch__name", "area", "floor", "code")
    rows = [_room_readiness_row(room, at) for room in queryset]
    if state == "CHECKIN_RISK":
        rows = [row for row in rows if row["checkinRisk"]]
    elif state == "STOP_SELL":
        rows = [row for row in rows if row["salesStatus"] == "STOP_SELL"]
    elif state:
        rows = [row for row in rows if row["state"] == state]
    return rows


def build_readiness_board(user, *, branch_id=None, query="", state="", at=None):
    rows = readiness_rows_for_user(
        user,
        branch_id=branch_id,
        query=query,
        state=state,
        at=at,
    )
    all_rows = readiness_rows_for_user(user, branch_id=branch_id, query=query, at=at)
    return {
        "rows": rows,
        "summary": {
            "total": len(all_rows),
            "ready": sum(row["state"] == "READY" for row in all_rows),
            "occupied": sum(row["state"] == "OCCUPIED" for row in all_rows),
            "notReady": sum(row["state"] == "NOT_READY" for row in all_rows),
            "blocked": sum(row["state"] == "BLOCKED" for row in all_rows),
            "checkinRisk": sum(row["checkinRisk"] for row in all_rows),
            "stopSell": sum(row["salesStatus"] == "STOP_SELL" for row in all_rows),
        },
    }


def build_daily_schedule(user, selected_date: date, *, branch_id=None):
    allowed_rooms = room_queryset_for_user(user).filter(branch__is_active=True)
    if branch_id:
        allowed_rooms = allowed_rooms.filter(branch_id=branch_id)
    room_ids = list(allowed_rooms.values_list("id", flat=True))
    bookings = list(
        Booking.objects.filter(room_id__in=room_ids)
        .exclude(status=Booking.Status.CANCELLED)
        .filter(Q(checkin_at__date=selected_date) | Q(checkout_at__date=selected_date))
        .select_related("branch", "room")
        .prefetch_related("special_request_items")
        .order_by("checkout_at", "checkin_at", "room__code")
    )
    booking_ids = [booking.id for booking in bookings]
    tasks_by_booking = defaultdict(list)
    for task in (
        HousekeepingTask.objects.filter(booking_id__in=booking_ids)
        .select_related("assignee", "room")
        .order_by("due_at", "code")
    ):
        tasks_by_booking[task.booking_id].append(task)
    blocking_room_ids = set(
        IssueTicket.objects.filter(room_id__in=room_ids, blocks_room_ready=True)
        .exclude(status__in=TERMINAL_ISSUE_STATUSES)
        .values_list("room_id", flat=True)
    )
    stop_sells_by_room = defaultdict(list)
    for stop_sell in (
        RoomStopSell.objects.filter(
            room_id__in=room_ids,
            status__in=OPEN_STOP_SELL_STATUSES,
        )
        .select_related("blocker")
        .order_by("starts_at", "created_at")
    ):
        stop_sells_by_room[stop_sell.room_id].append(stop_sell)

    rows = []
    missing_cleaning_count = 0
    checkin_risk_count = 0
    checkin_count = 0
    checkout_count = 0
    for booking in bookings:
        tasks = tasks_by_booking[booking.id]
        is_checkin = bool(booking.checkin_at and timezone.localdate(booking.checkin_at) == selected_date)
        is_checkout = bool(booking.checkout_at and timezone.localdate(booking.checkout_at) == selected_date)
        checkin_count += int(is_checkin)
        checkout_count += int(is_checkout)
        has_checkout_cleaning = any(
            task.task_type == HousekeepingTask.TaskType.CHECKOUT_CLEANING
            and task.status != HousekeepingTask.Status.CANCELLED
            for task in tasks
        )
        missing_cleaning = bool(is_checkout and not has_checkout_cleaning)
        missing_cleaning_count += int(missing_cleaning)
        task_still_open = any(
            task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
            and task.status not in TERMINAL_TASK_STATUSES
            for task in tasks
        )
        stop_sell = next(
            (
                item
                for item in stop_sells_by_room[booking.room_id]
                if stop_sell_overlaps(item, booking.checkin_at, booking.checkout_at)
            ),
            None,
        )
        checkin_risk = bool(
            is_checkin
            and (
                booking.room.status != Room.Status.READY
                or booking.room.is_locked
                or booking.room_id in blocking_room_ids
                or task_still_open
                or stop_sell
            )
        )
        checkin_risk_count += int(checkin_risk)
        rows.append(
            {
                "booking": booking,
                "canViewGuest": can_view_booking_guest(user, booking.branch),
                "tasks": tasks,
                "isCheckin": is_checkin,
                "isCheckout": is_checkout,
                "missingCleaning": missing_cleaning,
                "checkinRisk": checkin_risk,
                "stopSell": stop_sell,
            }
        )

    standalone_tasks = list(
        HousekeepingTask.objects.filter(
            room_id__in=room_ids,
            booking__isnull=True,
            scheduled_start_at__date=selected_date,
        )
        .select_related("branch", "room", "assignee")
        .order_by("scheduled_start_at", "room__code")
    )
    return {
        "date": selected_date,
        "rows": rows,
        "standaloneTasks": standalone_tasks,
        "summary": {
            "bookingCount": len(bookings),
            "checkinCount": checkin_count,
            "checkoutCount": checkout_count,
            "missingCleaningCount": missing_cleaning_count,
            "checkinRiskCount": checkin_risk_count,
            "standaloneTaskCount": len(standalone_tasks),
        },
    }


def build_room_profile(user, room_id, *, at=None):
    rows = readiness_rows_for_user(user, room_id=room_id, at=at)
    if not rows:
        return None
    readiness = rows[0]
    room = readiness["room"]
    bookings = list(
        room.bookings.exclude(status=Booking.Status.CANCELLED)
        .prefetch_related("special_request_items")
        .order_by("-checkin_at", "-created_at")[:12]
    )
    tasks = list(
        room.housekeeping_tasks.select_related("assignee", "booking", "branch")
        .prefetch_related("qc_rounds", "supply_requests", "issues")
        .order_by("-created_at")[:20]
    )
    issues = list(
        room.issues.select_related("task", "assigned_to", "reported_by")
        .order_by("-created_at")[:20]
    )
    blockers = list(
        room.operational_blockers.select_related(
            "issue", "created_by", "clearance_requested_by", "cleared_by"
        ).order_by("-starts_at", "-created_at")[:20]
    )
    stop_sells = list(
        room.stop_sells.select_related(
            "blocker", "created_by", "reopen_requested_by", "reopened_by"
        ).prefetch_related("history").order_by("-starts_at", "-created_at")[:20]
    )
    photos = list(
        room.housekeeping_photos.select_related("task", "uploaded_by", "checklist_item")
        .order_by("-captured_at", "-created_at")[:60]
    )

    timeline = []
    for booking in bookings:
        timeline.append(
            {
                "at": booking.updated_at,
                "kind": "booking",
                "title": f"Booking {booking.code}: {booking.get_status_display()}",
                "description": "Lịch nhận/trả phòng đã được cập nhật.",
            }
        )
    for task in tasks:
        timeline.append(
            {
                "at": task.updated_at,
                "kind": "task",
                "title": f"{task.code}: {task.get_status_display()}",
                "description": task.get_task_type_display(),
            }
        )
    for issue in issues:
        timeline.append(
            {
                "at": issue.resolved_at or issue.created_at,
                "kind": "issue",
                "title": f"Sự cố: {issue.get_status_display()}",
                "description": issue.description,
            }
        )
    for blocker in blockers:
        timeline.append(
            {
                "at": blocker.cleared_at or blocker.clearance_requested_at or blocker.created_at,
                "kind": "blocker",
                "title": f"Blocker {blocker.get_kind_display()}: {blocker.get_status_display()}",
                "description": blocker.reason,
            }
        )
    for stop_sell in stop_sells:
        timeline.append(
            {
                "at": stop_sell.reopened_at or stop_sell.reopen_requested_at or stop_sell.created_at,
                "kind": "stop-sell",
                "title": f"Dừng bán: {stop_sell.get_status_display()}",
                "description": stop_sell.reason,
            }
        )
    for photo in photos:
        timeline.append(
            {
                "at": photo.captured_at or photo.created_at,
                "kind": "photo",
                "title": f"Ảnh {photo.get_category_display().lower()}",
                "description": f"Từ công việc {photo.task.code}",
            }
        )
    timeline.sort(key=lambda item: item["at"] or timezone.now(), reverse=True)
    return {
        "readiness": readiness,
        "room": room,
        "bookings": bookings,
        "tasks": tasks,
        "issues": issues,
        "blockers": blockers,
        "stopSells": stop_sells,
        "photos": photos,
        "timeline": timeline[:80],
        "canViewGuest": can_view_booking_guest(user, room.branch),
        "canManageStopSell": can_manage_room_sales_status(user, room.branch),
    }
