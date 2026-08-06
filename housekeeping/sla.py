from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    HousekeepingActivityLog,
    HousekeepingTask,
    SLAEscalationEvent,
    SLAPolicy,
    TaskSLAState,
)
from .notifications import notify_task


THRESHOLD_RECIPIENTS = {
    5: "housekeeping",
    15: "housekeeping_lead",
    30: "manager",
}


def policy_for_task(task):
    policies = SLAPolicy.objects.filter(branch=task.branch, is_active=True)
    return (
        policies.filter(task_type=task.task_type, priority=task.priority).first()
        or policies.filter(task_type=task.task_type, priority="").first()
        or policies.filter(task_type="", priority=task.priority).first()
        or policies.filter(task_type="", priority="").first()
    )


@transaction.atomic
def ensure_sla_state(task):
    policy = policy_for_task(task)
    acceptance_minutes = policy.acceptance_minutes if policy else 5
    start_minutes = policy.start_minutes if policy else 15
    completion_minutes = policy.completion_minutes if policy else 45
    state, created = TaskSLAState.objects.select_for_update().get_or_create(task=task)
    if created or not state.policy_snapshot:
        state.policy = policy
        state.policy_snapshot = {
            "acceptanceMinutes": acceptance_minutes,
            "startMinutes": start_minutes,
            "completionMinutes": completion_minutes,
            "standardDurationMinutes": task.standard_duration_minutes or completion_minutes,
            "checkinRiskBufferMinutes": policy.checkin_risk_buffer_minutes if policy else 15,
            "excludeApprovedPauseTime": policy.exclude_approved_pause_time if policy else True,
            "escalationMinutes": policy.escalation_minutes if policy else [5, 15, 30],
        }
        state.acceptance_due_at = task.acceptance_due_at or task.created_at + timedelta(minutes=acceptance_minutes)
        state.start_due_at = task.start_due_at or task.scheduled_start_at + timedelta(minutes=start_minutes)
        state.completion_due_at = task.due_at or task.scheduled_start_at + timedelta(minutes=completion_minutes)
        state.save(
            update_fields=[
                "policy",
                "policy_snapshot",
                "acceptance_due_at",
                "start_due_at",
                "completion_due_at",
                "updated_at",
            ]
        )
    return state


def _deadline_overdue_minutes(actual_at, due_at, now):
    if due_at is None:
        return 0
    compare_at = actual_at or now
    return max(0, int((compare_at - due_at).total_seconds() // 60))


def _escalation_thresholds(raw_values):
    thresholds = set()
    for value in raw_values or []:
        try:
            threshold = int(value)
        except (TypeError, ValueError):
            continue
        if threshold > 0:
            thresholds.add(threshold)
    return sorted(thresholds or {5, 15, 30})


def _send_near_due_reminders(task, state, effective_completion_due, now, terminal):
    if terminal:
        return
    milestones = (
        ("acceptance", task.accepted_at, state.acceptance_due_at, "nhận việc"),
        ("start", task.started_at, state.start_due_at, "bắt đầu"),
        ("completion", task.completed_at, effective_completion_due, "hoàn thành"),
    )
    for code, actual_at, due_at, label in milestones:
        if actual_at or due_at is None:
            continue
        remaining_seconds = (due_at - now).total_seconds()
        if not 0 <= remaining_seconds <= 5 * 60:
            continue
        notify_task(
            task,
            "SLA_NEAR_DUE",
            f"Công việc {task.code} sắp quá hạn {label}",
            f"Phòng {task.room.code} còn dưới 5 phút trước thời hạn {label}.",
            deduplication_key=f"sla:{task.id}:near-due:{code}",
            users=[task.assignee] if task.assignee else None,
            roles={"housekeeping_lead"} if task.assignee is None else None,
            payload={"taskId": str(task.id), "milestone": code, "dueAt": due_at.isoformat()},
        )


@transaction.atomic
def evaluate_task_sla(task, *, at=None):
    now = at or timezone.now()
    # ``assignee`` is nullable, so select_related() uses a LEFT JOIN. PostgreSQL
    # cannot apply FOR UPDATE to that nullable join; only the task row needs to
    # be locked while SLA state and escalation records are evaluated.
    task = (
        HousekeepingTask.objects.select_for_update(of=("self",))
        .select_related("branch", "room", "assignee")
        .get(pk=task.pk)
    )
    state = ensure_sla_state(task)
    effective_completion_due = state.completion_due_at
    if effective_completion_due and state.policy_snapshot.get("excludeApprovedPauseTime", True):
        effective_completion_due += timedelta(seconds=state.excluded_pause_seconds)

    acceptance_overdue = _deadline_overdue_minutes(task.accepted_at, state.acceptance_due_at, now)
    start_overdue = _deadline_overdue_minutes(task.started_at, state.start_due_at, now)
    completion_overdue = _deadline_overdue_minutes(task.completed_at, effective_completion_due, now)
    terminal = task.status in {HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED}
    _send_near_due_reminders(task, state, effective_completion_due, now, terminal)
    if task.accepted_at is None and acceptance_overdue and not state.acceptance_breached_at:
        state.acceptance_breached_at = now
    elif task.accepted_at and state.acceptance_due_at and task.accepted_at > state.acceptance_due_at and not state.acceptance_breached_at:
        state.acceptance_breached_at = task.accepted_at
    if task.started_at is None and start_overdue and not terminal and not state.start_breached_at:
        state.start_breached_at = now
    elif task.started_at and state.start_due_at and task.started_at > state.start_due_at and not state.start_breached_at:
        state.start_breached_at = task.started_at
    if task.completed_at is None and completion_overdue and not terminal and not state.completion_breached_at:
        state.completion_breached_at = now
    elif task.completed_at and effective_completion_due and task.completed_at > effective_completion_due and not state.completion_breached_at:
        state.completion_breached_at = task.completed_at

    risk_buffer = state.policy_snapshot.get("checkinRiskBufferMinutes", 15)
    checkin_risk = bool(
        task.next_checkin_at
        and not terminal
        and (
            effective_completion_due is None
            or effective_completion_due >= task.next_checkin_at - timedelta(minutes=risk_buffer)
            or now >= task.next_checkin_at - timedelta(minutes=risk_buffer)
        )
    )
    if checkin_risk and not state.checkin_risk_at:
        state.checkin_risk_at = now
        if task.priority != HousekeepingTask.Priority.URGENT:
            previous_priority = task.priority
            task.priority = HousekeepingTask.Priority.URGENT
            task.version += 1
            task.save(update_fields=["priority", "version", "updated_at"])
            HousekeepingActivityLog.objects.create(
                task=task,
                user=None,
                branch=task.branch,
                action="SLA_CHECKIN_RISK_MARKED_URGENT",
                correlation_id=f"sla-checkin-risk-{task.id}",
                changes={"from": previous_priority, "to": task.priority},
            )
        notify_task(
            task,
            "SLA_CHECKIN_RISK",
            f"Nguy cơ trễ giờ nhận phòng: {task.room.code}",
            f"Công việc {task.code} có nguy cơ ảnh hưởng giờ nhận phòng tiếp theo.",
            deduplication_key=f"sla:{task.id}:checkin-risk",
            roles={"housekeeping_lead", "manager"},
            users=[task.assignee] if task.assignee else None,
            payload={"taskId": str(task.id), "nextCheckinAt": task.next_checkin_at.isoformat()},
        )

    max_overdue = max(acceptance_overdue, start_overdue, completion_overdue)
    escalation_minutes = _escalation_thresholds(
        state.policy_snapshot.get("escalationMinutes", [5, 15, 30])
    )
    for threshold in escalation_minutes:
        if max_overdue < threshold:
            continue
        recipient_role = THRESHOLD_RECIPIENTS.get(threshold, "manager")
        event, created = SLAEscalationEvent.objects.get_or_create(
            task=task,
            event_type="SLA_OVERDUE",
            threshold_minutes=threshold,
            recipient_role=recipient_role,
            defaults={
                "occurred_at": now,
                "payload": {"maxOverdueMinutes": max_overdue},
            },
        )
        if created:
            notify_task(
                task,
                "SLA_ESCALATION",
                f"Công việc {task.code} trễ thời hạn {threshold} phút",
                f"Phòng {task.room.code} cần được xử lý ngay.",
                deduplication_key=f"sla:{task.id}:overdue:{threshold}:{recipient_role}",
                roles=({recipient_role} if threshold != 5 or task.assignee is None else None),
                users=[task.assignee] if threshold == 5 and task.assignee else None,
                payload={"taskId": str(task.id), "thresholdMinutes": threshold},
            )
    state.last_evaluated_at = now
    state.save(
        update_fields=[
            "acceptance_breached_at",
            "start_breached_at",
            "completion_breached_at",
            "checkin_risk_at",
            "last_evaluated_at",
            "updated_at",
        ]
    )
    return state
