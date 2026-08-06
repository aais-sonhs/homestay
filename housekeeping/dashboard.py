from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from .models import HousekeepingTask


TERMINAL_STATUSES = {
    HousekeepingTask.Status.QC_APPROVED,
    HousekeepingTask.Status.CANCELLED,
}


def _sla_state(task):
    try:
        return task.sla_state
    except HousekeepingTask.sla_state.RelatedObjectDoesNotExist:
        return None


def _task_durations(task, at):
    if task.started_at is None:
        return {"elapsedSeconds": 0, "pauseSeconds": 0, "activeSeconds": 0, "slaActiveSeconds": 0}
    end_at = task.completed_at or at
    elapsed = max(0, int((end_at - task.started_at).total_seconds()))
    pause_seconds = 0
    excluded_seconds = 0
    for pause in task.pauses.all():
        pause_end = min(pause.resumed_at or at, end_at)
        duration = max(0, int((pause_end - pause.paused_at).total_seconds()))
        pause_seconds += duration
        if pause.excluded_from_sla:
            excluded_seconds += duration
    return {
        "elapsedSeconds": elapsed,
        "pauseSeconds": pause_seconds,
        "activeSeconds": max(0, elapsed - pause_seconds),
        "slaActiveSeconds": max(0, elapsed - excluded_seconds),
    }


def _completion_due(task, state):
    due_at = state.completion_due_at if state and state.completion_due_at else task.due_at
    if state and due_at and state.policy_snapshot.get("excludeApprovedPauseTime", True):
        due_at += timedelta(seconds=state.excluded_pause_seconds)
    return due_at


def _local_datetime_label(value):
    if value is None:
        return None
    return timezone.localtime(value).strftime("%H:%M %d/%m/%Y")


def _risk_row(task, at):
    state = _sla_state(task)
    due_at = _completion_due(task, state)
    terminal = task.status in TERMINAL_STATUSES
    overdue_minutes = 0
    near_due = False
    if due_at and not terminal:
        seconds = (due_at - at).total_seconds()
        overdue_minutes = max(0, int((-seconds) // 60))
        near_due = 0 <= seconds <= 15 * 60
    checkin_risk = bool(state and state.checkin_risk_at)
    if not checkin_risk and task.next_checkin_at and not terminal:
        buffer_minutes = 15
        if state:
            buffer_minutes = state.policy_snapshot.get("checkinRiskBufferMinutes", 15)
        checkin_risk = bool(
            (due_at and due_at >= task.next_checkin_at - timedelta(minutes=buffer_minutes))
            or at >= task.next_checkin_at - timedelta(minutes=buffer_minutes)
        )
    durations = _task_durations(task, at)
    return {
        "taskId": str(task.id),
        "taskCode": task.code,
        "branch": {"id": str(task.branch_id), "code": task.branch.code, "name": task.branch.name},
        "room": {"id": str(task.room_id), "code": task.room.code, "name": task.room.name},
        "assignee": (
            {
                "id": str(task.assignee_id),
                "username": task.assignee.username,
                "name": task.assignee.get_full_name() or task.assignee.username,
            }
            if task.assignee
            else None
        ),
        "shift": (
            {"id": str(task.shift_id), "code": task.shift.code, "name": task.shift.name}
            if task.shift
            else None
        ),
        "status": task.status,
        "statusLabel": task.get_status_display(),
        "priority": task.priority,
        "progressPercent": task.progress_percent,
        "standardDurationMinutes": (
            state.policy_snapshot.get("standardDurationMinutes")
            if state
            else task.standard_duration_minutes
        ),
        "completionDueAt": due_at.isoformat() if due_at else None,
        "completionDueLabel": _local_datetime_label(due_at),
        "nextCheckinAt": task.next_checkin_at.isoformat() if task.next_checkin_at else None,
        "nearDue": near_due,
        "overdue": overdue_minutes > 0,
        "overdueMinutes": overdue_minutes,
        "checkinRisk": checkin_risk,
        "breaches": {
            "acceptance": bool(state and state.acceptance_breached_at),
            "start": bool(state and state.start_breached_at),
            "completion": bool(state and state.completion_breached_at),
        },
        **durations,
    }


def build_sla_dashboard(queryset, *, at=None):
    at = at or timezone.now()
    tasks = list(
        queryset.select_related("sla_state", "branch", "room", "assignee", "shift")
        .prefetch_related("pauses")
    )
    rows = [_risk_row(task, at) for task in tasks]
    by_status = defaultdict(int)
    for row in rows:
        by_status[row["status"]] += 1
    risky = [row for row in rows if row["overdue"] or row["nearDue"] or row["checkinRisk"]]
    risky.sort(
        key=lambda row: (
            not row["checkinRisk"],
            not row["overdue"],
            -row["overdueMinutes"],
            row["completionDueAt"] or "",
            row["taskCode"],
        )
    )
    return {
        "generatedAt": at.isoformat(),
        "summary": {
            "totalTasks": len(rows),
            "inProgress": sum(
                row["status"]
                in {
                    HousekeepingTask.Status.IN_PROGRESS,
                    HousekeepingTask.Status.PAUSED,
                    HousekeepingTask.Status.WAITING_SUPPORT,
                }
                for row in rows
            ),
            "nearDue": sum(row["nearDue"] for row in rows),
            "overdue": sum(row["overdue"] for row in rows),
            "checkinRisk": sum(row["checkinRisk"] for row in rows),
            "acceptanceBreached": sum(row["breaches"]["acceptance"] for row in rows),
            "startBreached": sum(row["breaches"]["start"] for row in rows),
            "completionBreached": sum(row["breaches"]["completion"] for row in rows),
            "byStatus": dict(sorted(by_status.items())),
        },
        "tasks": risky,
    }


def build_performance_dashboard(queryset, *, at=None):
    at = at or timezone.now()
    tasks = list(
        queryset.select_related("sla_state", "branch", "room", "assignee", "shift")
        .prefetch_related("pauses", "rework_rounds")
    )
    groups = {}
    for task in tasks:
        key = (task.assignee_id, task.shift_id, task.branch_id)
        if key not in groups:
            groups[key] = {
                "employee": (
                    {
                        "id": str(task.assignee_id),
                        "username": task.assignee.username,
                        "name": task.assignee.get_full_name() or task.assignee.username,
                    }
                    if task.assignee
                    else None
                ),
                "shift": (
                    {"id": str(task.shift_id), "code": task.shift.code, "name": task.shift.name}
                    if task.shift
                    else None
                ),
                "branch": {"id": str(task.branch_id), "code": task.branch.code, "name": task.branch.name},
                "taskCount": 0,
                "completedCount": 0,
                "qcApprovedCount": 0,
                "slaBreachedCount": 0,
                "reworkRoundCount": 0,
                "progressTotal": 0,
                "activeSecondsTotal": 0,
                "pauseSecondsTotal": 0,
            }
        row = groups[key]
        state = _sla_state(task)
        durations = _task_durations(task, at)
        row["taskCount"] += 1
        row["completedCount"] += int(task.completed_at is not None)
        row["qcApprovedCount"] += int(task.status == HousekeepingTask.Status.QC_APPROVED)
        row["slaBreachedCount"] += int(
            bool(
                state
                and (
                    state.acceptance_breached_at
                    or state.start_breached_at
                    or state.completion_breached_at
                )
            )
        )
        row["reworkRoundCount"] += len(task.rework_rounds.all())
        row["progressTotal"] += task.progress_percent
        row["activeSecondsTotal"] += durations["activeSeconds"]
        row["pauseSecondsTotal"] += durations["pauseSeconds"]

    rows = []
    for row in groups.values():
        count = row["taskCount"]
        rows.append(
            {
                **{key: value for key, value in row.items() if not key.endswith("Total")},
                "completionRatePercent": round(row["completedCount"] * 100 / count, 2),
                "qcApprovalRatePercent": round(row["qcApprovedCount"] * 100 / count, 2),
                "averageProgressPercent": round(row["progressTotal"] / count, 2),
                "averageActiveSeconds": round(row["activeSecondsTotal"] / count),
                "averageActiveMinutes": round(row["activeSecondsTotal"] / count / 60, 1),
                "averagePauseSeconds": round(row["pauseSecondsTotal"] / count),
            }
        )
    rows.sort(
        key=lambda row: (
            row["branch"]["code"],
            row["shift"]["code"] if row["shift"] else "",
            row["employee"]["name"] if row["employee"] else "",
        )
    )
    return {"generatedAt": at.isoformat(), "rows": rows}
