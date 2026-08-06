from dataclasses import dataclass

from .models import HousekeepingActivityLog, HousekeepingTask, Room, TaskStatusHistory


class Action:
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    RETURN = "RETURN"
    START = "START"
    START_REWORK = "START_REWORK"
    PAUSE = "PAUSE"
    WAIT_SUPPORT = "WAIT_SUPPORT"
    RESUME = "RESUME"
    COMPLETE = "COMPLETE"
    SEND_TO_QC = "SEND_TO_QC"
    COMPLETE_WITHOUT_QC = "COMPLETE_WITHOUT_QC"
    QC_APPROVE = "QC_APPROVE"
    QC_REJECT = "QC_REJECT"
    REASSIGN = "REASSIGN"
    CANCEL = "CANCEL"


TRANSITIONS = {
    Action.ACCEPT: {
        HousekeepingTask.Status.UNASSIGNED: HousekeepingTask.Status.ACCEPTED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE: HousekeepingTask.Status.ACCEPTED,
    },
    Action.REJECT: {
        HousekeepingTask.Status.ASSIGNED: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE: HousekeepingTask.Status.UNASSIGNED,
    },
    Action.RETURN: {
        HousekeepingTask.Status.ASSIGNED: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.PENDING_ACCEPTANCE: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.ACCEPTED: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.IN_PROGRESS: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.PAUSED: HousekeepingTask.Status.UNASSIGNED,
        HousekeepingTask.Status.WAITING_SUPPORT: HousekeepingTask.Status.UNASSIGNED,
    },
    Action.START: {
        HousekeepingTask.Status.ACCEPTED: HousekeepingTask.Status.IN_PROGRESS,
    },
    Action.START_REWORK: {
        HousekeepingTask.Status.QC_REJECTED: HousekeepingTask.Status.IN_PROGRESS,
    },
    Action.PAUSE: {
        HousekeepingTask.Status.IN_PROGRESS: HousekeepingTask.Status.PAUSED,
    },
    Action.WAIT_SUPPORT: {
        HousekeepingTask.Status.IN_PROGRESS: HousekeepingTask.Status.WAITING_SUPPORT,
    },
    Action.RESUME: {
        HousekeepingTask.Status.PAUSED: HousekeepingTask.Status.IN_PROGRESS,
        HousekeepingTask.Status.WAITING_SUPPORT: HousekeepingTask.Status.IN_PROGRESS,
    },
    Action.COMPLETE: {
        HousekeepingTask.Status.IN_PROGRESS: HousekeepingTask.Status.COMPLETED,
    },
    Action.SEND_TO_QC: {
        HousekeepingTask.Status.COMPLETED: HousekeepingTask.Status.WAITING_QC,
    },
    Action.COMPLETE_WITHOUT_QC: {
        HousekeepingTask.Status.COMPLETED: HousekeepingTask.Status.QC_APPROVED,
    },
    Action.QC_APPROVE: {
        HousekeepingTask.Status.WAITING_QC: HousekeepingTask.Status.QC_APPROVED,
    },
    Action.QC_REJECT: {
        HousekeepingTask.Status.WAITING_QC: HousekeepingTask.Status.QC_REJECTED,
    },
    Action.REASSIGN: {
        status: HousekeepingTask.Status.PENDING_ACCEPTANCE
        for status in {
            HousekeepingTask.Status.UNASSIGNED,
            HousekeepingTask.Status.ASSIGNED,
            HousekeepingTask.Status.PENDING_ACCEPTANCE,
            HousekeepingTask.Status.ACCEPTED,
            HousekeepingTask.Status.IN_PROGRESS,
            HousekeepingTask.Status.PAUSED,
            HousekeepingTask.Status.WAITING_SUPPORT,
            HousekeepingTask.Status.QC_REJECTED,
        }
    },
    Action.CANCEL: {
        status: HousekeepingTask.Status.CANCELLED
        for status in HousekeepingTask.Status.values
        if status not in {HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED}
    },
}


ROOM_STATUS_BY_ACTION = {
    Action.START: Room.Status.CLEANING,
    Action.START_REWORK: Room.Status.CLEANING,
    Action.WAIT_SUPPORT: Room.Status.CLEANING_BLOCKED,
    Action.RESUME: Room.Status.CLEANING,
    Action.SEND_TO_QC: Room.Status.WAITING_QC,
    Action.COMPLETE_WITHOUT_QC: Room.Status.READY,
    Action.QC_APPROVE: Room.Status.READY,
    Action.QC_REJECT: Room.Status.REWORK_REQUIRED,
}


def _room_status_after_cancel(task, current_status):
    other_statuses = set(
        HousekeepingTask.objects.filter(room_id=task.room_id)
        .exclude(pk=task.pk)
        .exclude(status__in={HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED})
        .values_list("status", flat=True)
    )
    if HousekeepingTask.Status.WAITING_SUPPORT in other_statuses:
        return Room.Status.CLEANING_BLOCKED
    if other_statuses & {HousekeepingTask.Status.IN_PROGRESS, HousekeepingTask.Status.PAUSED}:
        return Room.Status.CLEANING
    if HousekeepingTask.Status.QC_REJECTED in other_statuses:
        return Room.Status.REWORK_REQUIRED
    if other_statuses & {HousekeepingTask.Status.COMPLETED, HousekeepingTask.Status.WAITING_QC}:
        return Room.Status.WAITING_QC
    if other_statuses:
        return Room.Status.WAITING_CLEANING
    if current_status in {
        Room.Status.DIRTY,
        Room.Status.WAITING_CLEANING,
        Room.Status.CLEANING,
        Room.Status.CLEANING_BLOCKED,
        Room.Status.WAITING_QC,
        Room.Status.REWORK_REQUIRED,
    }:
        return Room.Status.WAITING_CLEANING
    return current_status


def _sync_room_status(task, action):
    if action not in ROOM_STATUS_BY_ACTION and action != Action.CANCEL:
        return
    room = Room.objects.select_for_update().get(pk=task.room_id)
    if room.status == Room.Status.OUT_OF_SERVICE:
        task.room = room
        return
    target_status = (
        _room_status_after_cancel(task, room.status)
        if action == Action.CANCEL
        else ROOM_STATUS_BY_ACTION[action]
    )
    if room.status != target_status:
        room.status = target_status
        room.save(update_fields=["status"])
    task.room = room


@dataclass(frozen=True)
class TransitionResult:
    from_status: str
    to_status: str
    version: int


class InvalidTaskTransition(Exception):
    def __init__(self, action, from_status):
        self.action = action
        self.from_status = from_status
        super().__init__(f"Không thể thực hiện {action} từ trạng thái {from_status}.")


def target_status(action, from_status):
    try:
        return TRANSITIONS[action][from_status]
    except KeyError:
        raise InvalidTaskTransition(action, from_status) from None


def apply_transition(
    task,
    *,
    action,
    event,
    user,
    context,
    reason_code="",
    note="",
    changes=None,
    metadata=None,
    update_fields=None,
):
    from_status = task.status
    to_status = target_status(action, from_status)
    task.status = to_status
    task.version += 1
    fields = ["status", "version", "updated_at", *(update_fields or [])]
    task.save(update_fields=list(dict.fromkeys(fields)))
    _sync_room_status(task, action)
    TaskStatusHistory.objects.create(
        task=task,
        from_status=from_status,
        to_status=to_status,
        reason_code=reason_code,
        note=note,
        changed_by=user,
        task_version=task.version,
        metadata=metadata or {},
    )
    HousekeepingActivityLog.objects.create(
        task=task,
        user=user,
        branch=task.branch,
        action=event,
        reason_code=reason_code,
        from_status=from_status,
        to_status=to_status,
        ip_address=context.get("ip"),
        device_id=context.get("device_id", ""),
        correlation_id=context.get("correlation_id", ""),
        idempotency_key=context.get("idempotency_key", ""),
        changes=changes or {},
    )
    return TransitionResult(from_status, to_status, task.version)
