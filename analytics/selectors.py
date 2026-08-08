from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDate
from django.urls import reverse
from django.utils import timezone

from common.access import MANAGEMENT_ROLES, is_active_user
from housekeeping.models import Booking, HousekeepingTask, IssueTicket, OperatingExpense
from organizations.models import Room
from reservations.selectors import revenue_branch_queryset
from room_operations.models import RoomAsset, RoomBlocker, RoomStopSell
from room_operations.selectors import OPEN_BLOCKER_STATUSES, OPEN_STOP_SELL_STATUSES


MONEY_ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)
TERMINAL_TASK_STATUSES = {
    HousekeepingTask.Status.QC_APPROVED,
    HousekeepingTask.Status.CANCELLED,
}
TERMINAL_ISSUE_STATUSES = {
    IssueTicket.Status.RESOLVED,
    IssueTicket.Status.CANCELLED,
}
TECHNICAL_EXPENSE_TERMS = ("kỹ thuật", "bảo trì", "sửa", "maintenance", "repair")
HOUSEKEEPING_EXPENSE_TERMS = ("housekeeping", "buồng", "vệ sinh", "giặt", "dọn")


def can_view_owner_dashboard(user):
    return bool(is_active_user(user) and user.role in MANAGEMENT_ROLES)


def _day_bounds(day):
    current_timezone = timezone.get_current_timezone()
    starts_at = timezone.make_aware(datetime.combine(day, time.min), current_timezone)
    return starts_at, starts_at + timedelta(days=1)


def _month_start(day):
    return day.replace(day=1)


def _next_month_start(day):
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def _previous_mtd_bounds(day):
    current_start = _month_start(day)
    previous_last_day = current_start - timedelta(days=1)
    previous_start = previous_last_day.replace(day=1)
    previous_end_day = min(day.day, monthrange(previous_start.year, previous_start.month)[1])
    return previous_start, previous_start.replace(day=previous_end_day)


def _money_sum(queryset, expression="amount"):
    if isinstance(expression, str):
        expression = F(expression)
    return queryset.aggregate(
        total=Coalesce(Sum(expression), Value(MONEY_ZERO), output_field=MONEY_FIELD)
    )["total"]


def _booking_total_expression():
    return ExpressionWrapper(
        F("room_charge") + F("service_charge") - F("discount_amount"),
        output_field=MONEY_FIELD,
    )


def _category_query(terms):
    query = Q()
    for term in terms:
        query |= Q(category__icontains=term)
    return query


def _expense_category_query(category_code, legacy_terms):
    return Q(category_code=category_code) | (
        Q(category_code=OperatingExpense.CategoryCode.OTHER) & _category_query(legacy_terms)
    )


def _change(current, previous):
    if not previous:
        return {"available": False, "value": Decimal("0"), "direction": "flat"}
    value = ((current - previous) * Decimal("100") / previous).quantize(Decimal("0.1"))
    return {
        "available": True,
        "value": abs(value),
        "direction": "up" if value > 0 else ("down" if value < 0 else "flat"),
    }


def _percentage(part, total):
    if not total:
        return 0
    return round(float(Decimal(part) * Decimal("100") / Decimal(total)), 1)


def _chart_points(values, max_value, *, width=520, height=150, padding=8):
    plotted_values = list(values)
    if len(plotted_values) == 1:
        plotted_values.append(plotted_values[0])
    if not plotted_values:
        plotted_values = [MONEY_ZERO, MONEY_ZERO]
    scale = float(max_value or Decimal("1"))
    x_step = (width - padding * 2) / max(1, len(plotted_values) - 1)
    return " ".join(
        f"{padding + index * x_step:.1f},{height - padding - (float(value) / scale) * (height - padding * 2):.1f}"
        for index, value in enumerate(plotted_values)
    )


def _revenue_chart(revenue, selected_date, current_start_at, current_end_at, previous_start, previous_end):
    previous_start_at, _ = _day_bounds(previous_start)
    _, previous_end_at = _day_bounds(previous_end)

    def totals_by_day(queryset, starts_at, ends_at):
        return {
            row["chart_date"]: row["total"]
            for row in queryset.filter(checkout_at__gte=starts_at, checkout_at__lt=ends_at)
            .annotate(chart_date=TruncDate("checkout_at"))
            .values("chart_date")
            .annotate(
                total=Coalesce(
                    Sum(_booking_total_expression()),
                    Value(MONEY_ZERO),
                    output_field=MONEY_FIELD,
                )
            )
            .order_by("chart_date")
        }

    current_daily = totals_by_day(revenue, current_start_at, current_end_at)
    previous_daily = totals_by_day(revenue, previous_start_at, previous_end_at)
    current_values = []
    previous_values = []
    current_running = MONEY_ZERO
    previous_running = MONEY_ZERO
    for offset in range(selected_date.day):
        current_day = selected_date.replace(day=1) + timedelta(days=offset)
        previous_day = previous_start + timedelta(days=offset)
        current_running += current_daily.get(current_day, MONEY_ZERO)
        if previous_day <= previous_end:
            previous_running += previous_daily.get(previous_day, MONEY_ZERO)
        current_values.append(current_running)
        previous_values.append(previous_running)

    chart_max = max([MONEY_ZERO, *current_values, *previous_values])
    middle_day = max(1, (selected_date.day + 1) // 2)
    return {
        "currentPoints": _chart_points(current_values, chart_max),
        "previousPoints": _chart_points(previous_values, chart_max),
        "maxValue": chart_max,
        "middleValue": chart_max / Decimal("2"),
        "labels": (
            f"01/{selected_date:%m}",
            f"{middle_day:02d}/{selected_date:%m}",
            f"{selected_date.day:02d}/{selected_date:%m}",
        ),
    }


def _query_url(name, **params):
    values = {key: str(value) for key, value in params.items() if value not in (None, "")}
    base_url = reverse(name)
    return f"{base_url}?{urlencode(values)}" if values else base_url


def _scoped_url_params(selected_date, branch_id):
    return {"date": selected_date.isoformat(), "branchId": branch_id or ""}


def _task_summary(tasks, *, selected_date, branch_id, reference_at):
    completed = tasks.filter(
        Q(status=HousekeepingTask.Status.QC_APPROVED)
        | Q(status=HousekeepingTask.Status.COMPLETED, requires_qc=False)
    ).count()
    in_progress_statuses = {
        HousekeepingTask.Status.ACCEPTED,
        HousekeepingTask.Status.IN_PROGRESS,
        HousekeepingTask.Status.PAUSED,
        HousekeepingTask.Status.WAITING_SUPPORT,
        HousekeepingTask.Status.WAITING_QC,
    }
    unaccepted_statuses = {
        HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.ASSIGNED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE,
    }
    overdue = tasks.filter(due_at__lt=reference_at).exclude(status__in=TERMINAL_TASK_STATUSES).count()
    scope = _scoped_url_params(selected_date, branch_id)
    return {
        "total": tasks.count(),
        "completed": completed,
        "inProgress": tasks.filter(status__in=in_progress_statuses).count(),
        "unaccepted": tasks.filter(status__in=unaccepted_statuses).count(),
        "overdue": overdue,
        "rework": tasks.filter(status=HousekeepingTask.Status.QC_REJECTED).count(),
        "links": {
            "total": _query_url("housekeeping:task-list", **scope),
            "completed": _query_url("housekeeping:task-list", tab="done", **scope),
            "inProgress": _query_url("housekeeping:task-list", tab="in-progress", **scope),
            "unaccepted": _query_url("housekeeping:task-list", tab="open", **scope),
            "overdue": _query_url("housekeeping:task-list", overdue="true", **scope),
            "rework": _query_url("housekeeping:task-list", tab="qc-rework", **scope),
        },
    }


def _financial_summary(branches, selected_date, *, branch_id):
    day_start, day_end = _day_bounds(selected_date)
    current_month_start = _month_start(selected_date)
    current_month_start_at, _ = _day_bounds(current_month_start)
    _, current_mtd_end_at = _day_bounds(selected_date)
    previous_start, previous_end = _previous_mtd_bounds(selected_date)
    previous_start_at, _ = _day_bounds(previous_start)
    _, previous_end_at = _day_bounds(previous_end)

    revenue = Booking.objects.filter(branch__in=branches, checkout_at__isnull=False).exclude(
        status=Booking.Status.CANCELLED
    )
    today_revenue = _money_sum(
        revenue.filter(checkout_at__gte=day_start, checkout_at__lt=day_end),
        _booking_total_expression(),
    )
    month_revenue = _money_sum(
        revenue.filter(checkout_at__gte=current_month_start_at, checkout_at__lt=current_mtd_end_at),
        _booking_total_expression(),
    )
    previous_revenue = _money_sum(
        revenue.filter(checkout_at__gte=previous_start_at, checkout_at__lt=previous_end_at),
        _booking_total_expression(),
    )

    expenses = OperatingExpense.objects.filter(
        branch__in=branches,
        payment_status=OperatingExpense.PaymentStatus.PAID,
    )
    month_expenses = expenses.filter(
        expense_date__gte=current_month_start,
        expense_date__lte=selected_date,
    )
    previous_expenses = expenses.filter(expense_date__gte=previous_start, expense_date__lte=previous_end)
    total_expense = _money_sum(month_expenses)
    previous_total_expense = _money_sum(previous_expenses)
    today_expense = _money_sum(expenses.filter(expense_date=selected_date))
    housekeeping_expense = _money_sum(
        month_expenses.filter(
            _expense_category_query(
                OperatingExpense.CategoryCode.HOUSEKEEPING,
                HOUSEKEEPING_EXPENSE_TERMS,
            )
        )
    )
    technical_expense = _money_sum(
        month_expenses.filter(
            _expense_category_query(
                OperatingExpense.CategoryCode.TECHNICAL_MAINTENANCE,
                TECHNICAL_EXPENSE_TERMS,
            )
        )
    )
    other_expense = max(
        MONEY_ZERO,
        total_expense - housekeeping_expense - technical_expense,
    )
    housekeeping_percent = _percentage(housekeeping_expense, total_expense)
    technical_percent = _percentage(technical_expense, total_expense)
    technical_end_percent = min(100, housekeeping_percent + technical_percent)
    revenue_chart = _revenue_chart(
        revenue,
        selected_date,
        current_month_start_at,
        current_mtd_end_at,
        previous_start,
        previous_end,
    )
    channel_totals = {
        row["source"]: row["total"]
        for row in revenue.filter(
            checkout_at__gte=current_month_start_at,
            checkout_at__lt=current_mtd_end_at,
        )
        .values("source")
        .annotate(
            total=Coalesce(
                Sum(_booking_total_expression()),
                Value(MONEY_ZERO),
                output_field=MONEY_FIELD,
            )
        )
    }
    source_labels = dict(Booking.Source.choices)
    channel_breakdown = sorted(
        (
            {
                "code": source,
                "label": source_labels.get(source, source.replace("_", " ").title()),
                "amount": amount,
                "percent": _percentage(amount, month_revenue),
            }
            for source, amount in channel_totals.items()
            if amount
        ),
        key=lambda row: row["amount"],
        reverse=True,
    )[:4]
    while len(channel_breakdown) < 4:
        channel_breakdown.append(
            {"code": "EMPTY", "label": "Chưa có dữ liệu", "amount": MONEY_ZERO, "percent": 0}
        )
    channel_one_end = channel_breakdown[0]["percent"]
    channel_two_end = min(100, channel_one_end + channel_breakdown[1]["percent"])
    channel_three_end = min(100, channel_two_end + channel_breakdown[2]["percent"])
    query_params = {"branchId": branch_id or "", "year": selected_date.year}
    return {
        "todayRevenue": today_revenue,
        "todayExpense": today_expense,
        "monthRevenue": month_revenue,
        "housekeepingExpense": housekeeping_expense,
        "technicalExpense": technical_expense,
        "totalExpense": total_expense,
        "otherExpense": other_expense,
        "expenseRatio": _percentage(total_expense, month_revenue),
        "housekeepingPercent": housekeeping_percent,
        "technicalPercent": technical_percent,
        "technicalEndPercent": technical_end_percent,
        "otherPercent": _percentage(other_expense, total_expense),
        "chart": revenue_chart,
        "channelBreakdown": channel_breakdown,
        "channelOneEnd": channel_one_end,
        "channelTwoEnd": channel_two_end,
        "channelThreeEnd": channel_three_end,
        "revenueChange": _change(month_revenue, previous_revenue),
        "expenseChange": _change(total_expense, previous_total_expense),
        "monthLabel": selected_date.strftime("%m/%Y"),
        "comparisonLabel": f"cùng {selected_date.day} ngày tháng trước",
        "revenueUrl": _query_url(
            "reservations:revenue-daily",
            branchId=branch_id or "",
            from_date=current_month_start.isoformat(),
            to_date=selected_date.isoformat(),
        ),
        "costUrl": _query_url("reservations:costs-dashboard", **query_params),
        "expenseUrl": _query_url(
            "reservations:expense-list",
            branchId=branch_id or "",
            from_date=current_month_start.isoformat(),
            to_date=selected_date.isoformat(),
        ),
    }


def build_owner_dashboard(user, selected_date, *, branch_id=None, at=None):
    at = at or timezone.now()
    branches = revenue_branch_queryset(user)
    if branch_id:
        branches = branches.filter(pk=branch_id)
    day_start, day_end = _day_bounds(selected_date)
    today = timezone.localdate(at)
    if selected_date < today:
        reference_at = day_end - timedelta(microseconds=1)
    elif selected_date > today:
        reference_at = day_start
    else:
        reference_at = at

    rooms = list(
        Room.objects.filter(branch__in=branches, branch__is_active=True)
        .select_related("branch")
        .order_by("branch__name", "code")
    )
    room_by_id = {room.id: room for room in rooms}
    room_ids = set(room_by_id)
    bookings = Booking.objects.filter(branch__in=branches).exclude(status=Booking.Status.CANCELLED)
    daily_bookings = bookings.filter(
        Q(checkin_at__gte=day_start, checkin_at__lt=day_end)
        | Q(checkout_at__gte=day_start, checkout_at__lt=day_end)
    ).select_related("branch", "room")
    checkins = list(daily_bookings.filter(checkin_at__gte=day_start, checkin_at__lt=day_end).order_by("checkin_at"))
    checkouts = list(daily_bookings.filter(checkout_at__gte=day_start, checkout_at__lt=day_end).order_by("checkout_at"))

    active_stop_sells = RoomStopSell.objects.filter(
        branch__in=branches,
        room_id__in=room_ids,
        status__in=OPEN_STOP_SELL_STATUSES,
        starts_at__lte=reference_at,
    ).select_related("room", "branch")
    stop_sell_room_ids = set(active_stop_sells.values_list("room_id", flat=True))
    active_blockers = RoomBlocker.objects.filter(
        branch__in=branches,
        room_id__in=room_ids,
        status__in=OPEN_BLOCKER_STATUSES,
        starts_at__lte=reference_at,
    )
    blocking_room_ids = set(active_blockers.values_list("room_id", flat=True))
    maintenance_blocked_room_ids = set(
        active_blockers.filter(kind=RoomBlocker.Kind.MAINTENANCE).values_list("room_id", flat=True)
    )
    open_issues = IssueTicket.objects.filter(room_id__in=room_ids).exclude(
        status__in=TERMINAL_ISSUE_STATUSES
    ).select_related("room", "task", "assigned_to")
    blocking_issue_room_ids = set(
        open_issues.filter(blocks_room_ready=True).values_list("room_id", flat=True)
    )
    open_tasks = HousekeepingTask.objects.filter(branch__in=branches).exclude(
        status__in=TERMINAL_TASK_STATUSES
    )
    open_tasks_by_room = defaultdict(list)
    for task in open_tasks.only("room_id", "due_at", "task_type"):
        open_tasks_by_room[task.room_id].append(task)

    occupied_day_room_ids = set(
        bookings.filter(checkin_at__lt=day_end, checkout_at__gt=day_start)
        .values_list("room_id", flat=True)
        .distinct()
    )
    if selected_date == today:
        occupied_room_ids = {
            room.id for room in rooms if room.is_guest_occupied
        } | set(
            bookings.filter(status=Booking.Status.CHECKED_IN).values_list("room_id", flat=True)
        )
    else:
        occupied_room_ids = occupied_day_room_ids
    maintenance_room_ids = {
        room.id for room in rooms if room.status == Room.Status.OUT_OF_SERVICE
    } | stop_sell_room_ids | maintenance_blocked_room_ids
    occupied_bucket = occupied_room_ids - maintenance_room_ids
    ready_room_ids = {
        room.id
        for room in rooms
        if room.id not in maintenance_room_ids
        and room.id not in occupied_bucket
        and room.status == Room.Status.READY
    }
    waiting_room_ids = room_ids - maintenance_room_ids - occupied_bucket - ready_room_ids
    sellable_rooms = max(len(occupied_day_room_ids), len(rooms) - len(maintenance_room_ids))
    occupancy_percent = round(
        len(occupied_day_room_ids) * 100 / sellable_rooms, 1
    ) if sellable_rooms else 0

    scope = _scoped_url_params(selected_date, branch_id)
    room_summary = {
        "total": len(rooms),
        "occupied": len(occupied_bucket),
        "ready": len(ready_room_ids),
        "waitingCleaning": len(waiting_room_ids),
        "maintenance": len(maintenance_room_ids),
        "occupancyPercent": occupancy_percent,
        "sellable": sellable_rooms,
        "links": {
            "total": _query_url("room_operations:room-readiness", branchId=branch_id or ""),
            "occupied": _query_url("room_operations:room-readiness", branchId=branch_id or "", state="OCCUPIED"),
            "ready": _query_url("room_operations:room-readiness", branchId=branch_id or "", state="READY"),
            "waitingCleaning": _query_url("room_operations:room-readiness", branchId=branch_id or "", state="NOT_READY"),
            "maintenance": _query_url("room_operations:room-readiness", branchId=branch_id or "", state="BLOCKED"),
        },
    }
    room_summary.update(
        {
            "occupiedPercent": _percentage(len(occupied_bucket), len(rooms)),
            "readyPercent": _percentage(len(ready_room_ids), len(rooms)),
            "waitingPercent": _percentage(len(waiting_room_ids), len(rooms)),
            "maintenancePercent": _percentage(len(maintenance_room_ids), len(rooms)),
        }
    )
    room_summary["readyEndPercent"] = min(
        100,
        room_summary["occupiedPercent"] + room_summary["readyPercent"],
    )
    room_summary["waitingEndPercent"] = min(
        100,
        room_summary["readyEndPercent"] + room_summary["waitingPercent"],
    )

    checkin_risks = []
    for booking in checkins:
        if booking.status != Booking.Status.BOOKED:
            continue
        reasons = []
        room = booking.room
        if room.status != Room.Status.READY:
            reasons.append(room.get_status_display())
        if room.id in stop_sell_room_ids:
            reasons.append("đang dừng bán")
        if room.id in blocking_room_ids or room.id in blocking_issue_room_ids:
            reasons.append("có sự cố/blocker")
        if any(
            task.due_at <= booking.checkin_at
            and task.task_type != HousekeepingTask.TaskType.CHECKOUT_CLEANING
            for task in open_tasks_by_room.get(room.id, [])
        ):
            reasons.append("còn công việc chưa hoàn tất")
        if not reasons:
            continue
        checkin_risks.append(
            {
                "booking": booking,
                "room": room,
                "reasons": reasons,
                "reasonLabel": " · ".join(dict.fromkeys(reasons)),
                "url": reverse("room_operations:room-profile", args=[room.id]),
            }
        )

    task_by_booking = {}
    checkout_booking_ids = [booking.id for booking in checkouts]
    for task in HousekeepingTask.objects.filter(
        booking_id__in=checkout_booking_ids,
        task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
    ).order_by("due_at"):
        task_by_booking.setdefault(task.booking_id, []).append(task)
    checkout_pending = []
    for booking in checkouts:
        if booking.status != Booking.Status.CHECKED_OUT:
            continue
        cleaning_tasks = task_by_booking.get(booking.id, [])
        valid_cleaning_tasks = [
            task for task in cleaning_tasks if task.status != HousekeepingTask.Status.CANCELLED
        ]
        housekeeping_done = bool(valid_cleaning_tasks) and all(
            task.status == HousekeepingTask.Status.QC_APPROVED
            or (task.status == HousekeepingTask.Status.COMPLETED and not task.requires_qc)
            for task in valid_cleaning_tasks
        )
        if housekeeping_done and booking.room.status == Room.Status.READY:
            continue
        active_task = next(
            (task for task in valid_cleaning_tasks if task.status not in TERMINAL_TASK_STATUSES),
            None,
        )
        checkout_pending.append(
            {
                "booking": booking,
                "room": booking.room,
                "task": active_task,
                "url": (
                    reverse("housekeeping:task-detail", args=[active_task.id])
                    if active_task
                    else reverse("room_operations:room-profile", args=[booking.room_id])
                ),
                "reasonLabel": (
                    active_task.get_status_display()
                    if active_task
                    else "Chưa có công việc dọn hoàn tất"
                ),
            }
        )

    arrival_departure = {
        "checkinTotal": len(checkins),
        "checkinDone": sum(
            booking.status in {Booking.Status.CHECKED_IN, Booking.Status.CHECKED_OUT}
            for booking in checkins
        ),
        "checkinPending": sum(booking.status == Booking.Status.BOOKED for booking in checkins),
        "checkoutTotal": len(checkouts),
        "checkoutDone": sum(booking.status == Booking.Status.CHECKED_OUT for booking in checkouts),
        "checkoutPending": sum(booking.status != Booking.Status.CHECKED_OUT for booking in checkouts),
        "checkinRisks": checkin_risks,
        "checkoutHousekeepingPending": checkout_pending,
        "scheduleUrl": _query_url("room_operations:schedule", **scope),
    }

    daily_tasks = HousekeepingTask.objects.filter(
        branch__in=branches,
        scheduled_start_at__gte=day_start,
        scheduled_start_at__lt=day_end,
    )
    task_summary = _task_summary(
        daily_tasks,
        selected_date=selected_date,
        branch_id=branch_id,
        reference_at=reference_at,
    )

    month_start = _month_start(selected_date)
    next_month = _next_month_start(selected_date)
    assets = RoomAsset.objects.filter(branch__in=branches, is_active=True)
    maintenance_due_assets = assets.filter(
        next_maintenance_at__isnull=False,
        next_maintenance_at__lte=selected_date,
    ).exclude(status=RoomAsset.Status.OUT_OF_SERVICE)
    monthly_incidents = IssueTicket.objects.filter(
        room_id__in=room_ids,
        created_at__date__gte=month_start,
        created_at__date__lt=next_month,
    )
    monthly_paid_expenses = OperatingExpense.objects.filter(
        branch__in=branches,
        payment_status=OperatingExpense.PaymentStatus.PAID,
        expense_date__gte=month_start,
        expense_date__lte=selected_date,
    )
    technical_cost = _money_sum(
        monthly_paid_expenses.filter(
            _expense_category_query(
                OperatingExpense.CategoryCode.TECHNICAL_MAINTENANCE,
                TECHNICAL_EXPENSE_TERMS,
            )
        )
    )
    technical = {
        "operational": assets.filter(status=RoomAsset.Status.OPERATIONAL).count(),
        "fault": assets.filter(status=RoomAsset.Status.FAULT).count(),
        "maintenance": assets.filter(status=RoomAsset.Status.MAINTENANCE).count(),
        "maintenanceDue": maintenance_due_assets.count(),
        "monthlyIncidents": monthly_incidents.count(),
        "monthlyCost": technical_cost,
        "assetUrl": _query_url("room_operations:asset-list", branchId=branch_id or ""),
        "faultUrl": _query_url("room_operations:asset-list", branchId=branch_id or "", status=RoomAsset.Status.FAULT),
        "maintenanceDueUrl": _query_url("room_operations:asset-list", branchId=branch_id or "", maintenanceDue="true"),
        "issueUrl": reverse("housekeeping:support-queue"),
    }

    alerts = []
    for row in checkin_risks:
        minutes_until = int((row["booking"].checkin_at - at).total_seconds() // 60) if row["booking"].checkin_at else 99999
        level = "HIGH" if selected_date == today and minutes_until <= 240 else "MEDIUM"
        alerts.append(
            {
                "level": level,
                "title": f"{row['room'].code} check-in {timezone.localtime(row['booking'].checkin_at):%H:%M} nhưng chưa sẵn sàng",
                "description": row["reasonLabel"],
                "url": row["url"],
                "sortAt": row["booking"].checkin_at,
            }
        )
    issue_priority = {
        HousekeepingTask.Priority.URGENT: 0,
        HousekeepingTask.Priority.HIGH: 1,
        HousekeepingTask.Priority.NORMAL: 2,
        HousekeepingTask.Priority.LOW: 3,
    }
    prioritized_issues = sorted(
        open_issues,
        key=lambda issue: (
            not issue.blocks_room_ready,
            issue_priority.get(issue.severity, 4),
            issue.created_at,
        ),
    )[:4]
    for issue in prioritized_issues:
        level = "HIGH" if issue.blocks_room_ready or issue.severity in {
            HousekeepingTask.Priority.HIGH,
            HousekeepingTask.Priority.URGENT,
        } else "MEDIUM"
        alerts.append(
            {
                "level": level,
                "title": f"{issue.room.code} · {issue.issue_type.replace('_', ' ').capitalize()}",
                "description": issue.description,
                "url": reverse("housekeeping:task-detail", args=[issue.task_id]),
                "sortAt": issue.created_at,
            }
        )
    if task_summary["overdue"]:
        alerts.append(
            {
                "level": "HIGH",
                "title": f"{task_summary['overdue']} công việc đã quá SLA",
                "description": "Cần điều phối hoặc cập nhật nguyên nhân chậm tiến độ.",
                "url": task_summary["links"]["overdue"],
                "sortAt": reference_at,
            }
        )
    if stop_sell_room_ids:
        alerts.append(
            {
                "level": "LOW",
                "title": f"{len(stop_sell_room_ids)} phòng đang dừng bán",
                "description": "Kiểm tra tiến độ xử lý và xác nhận mở bán lại khi đủ điều kiện.",
                "url": _query_url("room_operations:stop-sell-list", branchId=branch_id or "", status=RoomStopSell.Status.ACTIVE),
                "sortAt": reference_at,
            }
        )
    if technical["maintenanceDue"]:
        alerts.append(
            {
                "level": "MEDIUM",
                "title": f"{technical['maintenanceDue']} thiết bị đến hạn bảo trì",
                "description": "Lập lịch bảo trì để tránh phát sinh dừng bán ngoài kế hoạch.",
                "url": technical["maintenanceDueUrl"],
                "sortAt": reference_at,
            }
        )
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    alerts.sort(key=lambda alert: (priority_order[alert["level"]], alert["sortAt"]))

    financial = _financial_summary(branches, selected_date, branch_id=branch_id)
    financial["occupancyPercent"] = occupancy_percent
    current_month_start_at, _ = _day_bounds(_month_start(selected_date))
    _, current_mtd_end_at = _day_bounds(selected_date)
    branch_performance = []
    for branch in branches:
        branch_room_ids = {
            room.id for room in rooms if room.branch_id == branch.id
        }
        branch_occupied = len(branch_room_ids & occupied_day_room_ids)
        branch_maintenance = len(branch_room_ids & maintenance_room_ids)
        branch_sellable = max(
            branch_occupied,
            len(branch_room_ids) - branch_maintenance,
        )
        branch_performance.append(
            {
                "branch": branch,
                "revenue": _money_sum(
                    bookings.filter(
                        branch=branch,
                        checkout_at__gte=current_month_start_at,
                        checkout_at__lt=current_mtd_end_at,
                    ),
                    _booking_total_expression(),
                ),
                "occupancyPercent": (
                    round(branch_occupied * 100 / branch_sellable, 1)
                    if branch_sellable
                    else 0
                ),
                "url": _query_url(
                    "analytics:owner-dashboard",
                    date=selected_date.isoformat(),
                    branchId=branch.id,
                ),
            }
        )
    branch_performance.sort(
        key=lambda row: (row["revenue"], row["occupancyPercent"]),
        reverse=True,
    )
    return {
        "room": room_summary,
        "arrivalDeparture": arrival_departure,
        "tasks": task_summary,
        "alerts": alerts[:10],
        "technical": technical,
        "financial": financial,
        "branchPerformance": branch_performance[:3],
        "updatedAt": at,
        "selectedDate": selected_date,
    }
