from django.utils import timezone

from accounts.models import User
from common.display import localized_system_text
from housekeeping.models import HousekeepingTask, TaskChecklistItem
from common.access import Capability, decide_task_capability


def iso_datetime(value):
    return timezone.localtime(value).isoformat() if value else None


def user_data(user):
    if not user:
        return None
    return {
        "id": str(user.id),
        "username": user.username,
        "name": user.get_full_name() or user.username,
    }


def _allowed(user, task, capability):
    return decide_task_capability(user, task, capability).allowed


def task_capabilities(user, task):
    status = task.status
    owner = task.assignee_id == user.id
    try:
        allow_return_after_start = task.branch.housekeeping_policy.allow_return_after_start
    except AttributeError:
        allow_return_after_start = False
    return {
        "accept": _allowed(user, task, Capability.ACCEPT)
        and status in {HousekeepingTask.Status.UNASSIGNED, HousekeepingTask.Status.PENDING_ACCEPTANCE},
        "reject": _allowed(user, task, Capability.RETURN)
        and owner
        and status in {HousekeepingTask.Status.ASSIGNED, HousekeepingTask.Status.PENDING_ACCEPTANCE},
        "return": _allowed(user, task, Capability.RETURN)
        and owner
        and status in {
            HousekeepingTask.Status.ASSIGNED,
            HousekeepingTask.Status.PENDING_ACCEPTANCE,
            HousekeepingTask.Status.ACCEPTED,
        }
        or (
            _allowed(user, task, Capability.RETURN)
            and owner
            and allow_return_after_start
            and status
            in {
                HousekeepingTask.Status.IN_PROGRESS,
                HousekeepingTask.Status.PAUSED,
                HousekeepingTask.Status.WAITING_SUPPORT,
            }
        ),
        "start": _allowed(user, task, Capability.START)
        and owner
        and status in {HousekeepingTask.Status.ACCEPTED, HousekeepingTask.Status.QC_REJECTED},
        "update": _allowed(user, task, Capability.UPDATE)
        and owner
        and status == HousekeepingTask.Status.IN_PROGRESS,
        "pause": _allowed(user, task, Capability.PAUSE)
        and owner
        and status == HousekeepingTask.Status.IN_PROGRESS,
        "resume": _allowed(user, task, Capability.RESUME)
        and owner
        and status in {HousekeepingTask.Status.PAUSED, HousekeepingTask.Status.WAITING_SUPPORT},
        "complete": _allowed(user, task, Capability.COMPLETE)
        and owner
        and status == HousekeepingTask.Status.IN_PROGRESS,
        "reassign": _allowed(user, task, Capability.ASSIGN)
        and status not in {
            HousekeepingTask.Status.COMPLETED,
            HousekeepingTask.Status.WAITING_QC,
            HousekeepingTask.Status.QC_APPROVED,
            HousekeepingTask.Status.CANCELLED,
        },
        "cancel": _allowed(user, task, Capability.CANCEL)
        and status not in {HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED},
        "changePriority": _allowed(user, task, Capability.CHANGE_PRIORITY)
        and status not in {HousekeepingTask.Status.QC_APPROVED, HousekeepingTask.Status.CANCELLED},
        "qcReview": _allowed(user, task, Capability.QC_REVIEW)
        and status == HousekeepingTask.Status.WAITING_QC,
        "acceptChecklistFailure": _allowed(user, task, Capability.ASSIGN),
    }


def _checklist_summary(task):
    if hasattr(task, "api_required_count"):
        return {
            "totalRequired": task.api_required_count,
            "completedRequired": task.api_completed_required_count,
        }
    required = task.checklist_items.filter(is_required=True)
    return {
        "totalRequired": required.count(),
        "completedRequired": required.filter(status=TaskChecklistItem.Status.COMPLETED).count(),
    }


def task_data(task, user, *, detail=False, request=None):
    booking_code = task.booking.code if task.booking_id and task.booking else task.booking_code
    data = {
        "id": str(task.id),
        "taskId": str(task.id),
        "code": task.code,
        "room": {
            "id": str(task.room_id),
            "code": task.room.code,
            "name": task.room.name,
            "floor": task.room.floor,
            "area": task.room.area,
            "areaId": str(task.room.area_ref_id) if task.room.area_ref_id else None,
            "roomType": task.room.room_type,
            "status": task.room.status,
        },
        "roomStatus": task.room.status,
        "branch": {
            "id": str(task.branch_id),
            "code": task.branch.code,
            "name": task.branch.name,
        },
        "bookingCode": booking_code,
        "taskType": task.task_type,
        "taskTypeLabel": task.get_task_type_display(),
        "priority": task.priority,
        "status": task.status,
        "statusLabel": task.get_status_display(),
        "progressPercent": task.progress_percent,
        "scheduledStartAt": iso_datetime(task.scheduled_start_at),
        "acceptanceDueAt": iso_datetime(task.acceptance_due_at),
        "startDueAt": iso_datetime(task.start_due_at),
        "dueAt": iso_datetime(task.due_at),
        "nextCheckinAt": iso_datetime(task.next_checkin_at),
        "acceptedAt": iso_datetime(task.accepted_at),
        "startedAt": iso_datetime(task.started_at),
        "completedAt": iso_datetime(task.completed_at),
        "lastProgressAt": iso_datetime(task.last_progress_at),
        "assignee": user_data(task.assignee),
        "assignedBy": user_data(task.assigned_by),
        "updatedBy": user_data(task.updated_by),
        "shift": {
            "id": str(task.shift_id),
            "code": task.shift.code,
            "name": task.shift.name,
            "startsAt": iso_datetime(task.shift.starts_at),
            "endsAt": iso_datetime(task.shift.ends_at),
        }
        if task.shift
        else None,
        "team": {
            "id": str(task.team_id),
            "code": task.team.code,
            "name": task.team.name,
        }
        if task.team
        else None,
        "area": {
            "id": str(task.area_id),
            "code": task.area.code,
            "name": task.area.name,
        }
        if task.area
        else ({
            "id": str(task.room.area_ref_id),
            "code": task.room.area_ref.code,
            "name": task.room.area_ref.name,
        } if task.room.area_ref_id else None),
        "requiredSkills": [
            {"id": str(skill.id), "code": skill.code, "name": skill.name}
            for skill in task.required_skills.all()
        ],
        "isOverdue": task.is_overdue,
        "isCheckinRisk": bool(task.next_checkin_at and task.due_at >= task.next_checkin_at),
        "guestInRoom": task.guest_in_room or task.room.is_guest_occupied,
        "specialRequest": task.special_request,
        "note": task.note,
        "checklistSummary": _checklist_summary(task),
        "photoCount": getattr(task, "api_photo_count", None)
        if hasattr(task, "api_photo_count")
        else task.photos.count(),
        "version": task.version,
        "capabilities": task_capabilities(user, task),
    }
    if not detail:
        return data

    booking = None
    if task.booking_id and task.booking:
        booking = {
            "id": str(task.booking_id),
            "code": task.booking.code,
            "status": task.booking.status,
            "checkinAt": iso_datetime(task.booking.checkin_at),
            "checkoutAt": iso_datetime(task.booking.checkout_at),
            "guestCount": task.booking.guest_count,
        }
        if user.role in {User.Role.FOUNDER, User.Role.MANAGER, User.Role.CUSTOMER_SERVICE}:
            booking["guestName"] = task.booking.guest_name
            booking["guestPhone"] = task.booking.guest_phone

    def photo_data(photo):
        url = photo.image.url if photo.image else None
        if url and request:
            url = request.build_absolute_uri(url)
        return {
            "id": str(photo.id),
            "category": photo.category,
            "source": photo.source,
            "url": url,
            "checklistItemId": str(photo.checklist_item_id) if photo.checklist_item_id else None,
            "capturedAt": iso_datetime(photo.captured_at),
            "uploadedAt": iso_datetime(photo.created_at),
            "uploadedBy": user_data(photo.uploaded_by),
            "clientId": photo.client_id,
            "checksum": photo.checksum,
            "syncStatus": photo.sync_status,
            "location": {
                "latitude": str(photo.latitude),
                "longitude": str(photo.longitude),
                "accuracyMeters": str(photo.accuracy_meters) if photo.accuracy_meters is not None else None,
            }
            if photo.latitude is not None and photo.longitude is not None
            else None,
            "metadata": photo.metadata,
        }

    data.update(
        {
            "booking": booking,
            "shift": {
                "id": str(task.shift_id),
                "code": task.shift.code,
                "name": task.shift.name,
                "startsAt": iso_datetime(task.shift.starts_at),
                "endsAt": iso_datetime(task.shift.ends_at),
            }
            if task.shift
            else None,
            "team": {
                "id": str(task.team_id),
                "code": task.team.code,
                "name": task.team.name,
            }
            if task.team
            else None,
            "area": {
                "id": str(task.area_id),
                "code": task.area.code,
                "name": task.area.name,
            }
            if task.area
            else None,
            "checklistTemplateVersion": {
                "id": str(task.checklist_template_version_id),
                "label": task.checklist_template_version.version_label,
            }
            if task.checklist_template_version_id
            else None,
            "checklist": [
                {
                    "id": str(item.id),
                    "key": item.definition_key,
                    "group": item.group_name,
                    "title": item.title,
                    "type": item.item_type,
                    "required": item.is_required,
                    "requiresPhoto": item.requires_photo,
                    "options": item.options_snapshot,
                    "validationRules": item.validation_snapshot,
                    "status": item.status,
                    "value": item.value,
                    "note": item.note,
                    "failureReason": item.failure_reason,
                    "failureIssueId": str(item.failure_issue_id) if item.failure_issue_id else None,
                    "failureAcceptedBy": user_data(item.failure_accepted_by),
                    "failureAcceptedAt": iso_datetime(item.failure_accepted_at),
                    "completedBy": user_data(item.completed_by),
                    "completedAt": iso_datetime(item.completed_at),
                    "updateVersion": item.update_version,
                    "photos": [photo_data(photo) for photo in item.photos.all()],
                }
                for item in task.checklist_items.all()
            ],
            "photos": [photo_data(photo) for photo in task.photos.all()],
            "supplyRequests": [
                {
                    "id": str(supply.id),
                    "status": supply.status,
                    "priority": supply.priority,
                    "note": supply.note,
                    "blocksCompletion": supply.blocks_completion,
                    "requestedAt": iso_datetime(supply.created_at),
                    "items": [
                        {
                            "inventoryItemId": item.inventory_item_id,
                            "name": item.item_name,
                            "quantity": str(item.quantity),
                            "unit": item.unit,
                        }
                        for item in supply.items.all()
                    ],
                }
                for supply in task.supply_requests.all()
            ],
            "issues": [
                {
                    "id": str(issue.id),
                    "type": issue.issue_type,
                    "severity": issue.severity,
                    "description": issue.description,
                    "blocksRoomReady": issue.blocks_room_ready,
                    "status": issue.status,
                    "reportedBy": user_data(issue.reported_by),
                    "reportedAt": iso_datetime(issue.created_at),
                    "resolvedAt": iso_datetime(issue.resolved_at),
                }
                for issue in task.issues.all()
            ],
            "assignments": [
                {
                    "id": str(assignment.id),
                    "assignee": user_data(assignment.assignee),
                    "assignedBy": user_data(assignment.assigned_by),
                    "status": assignment.status,
                    "isCurrent": assignment.is_current,
                    "reasonCode": assignment.reason_code,
                    "note": assignment.note,
                    "assignedAt": iso_datetime(assignment.assigned_at),
                    "acceptedAt": iso_datetime(assignment.accepted_at),
                    "endedAt": iso_datetime(assignment.ended_at),
                }
                for assignment in task.assignments.all()
            ],
            "handovers": [
                {
                    "id": str(handover.id),
                    "fromUser": user_data(handover.from_user),
                    "toUser": user_data(handover.to_user),
                    "fromShiftId": str(handover.from_shift_id) if handover.from_shift_id else None,
                    "toShiftId": str(handover.to_shift_id) if handover.to_shift_id else None,
                    "note": handover.note,
                    "reconfirmRequiredItems": handover.reconfirm_required_items,
                    "handedOverAt": iso_datetime(handover.handed_over_at),
                }
                for handover in task.handovers.all()
            ],
            "qcRounds": [
                {
                    "id": str(qc.id),
                    "round": qc.round_number,
                    "status": qc.status,
                    "reason": qc.reason,
                    "note": qc.note,
                    "reviewer": user_data(qc.reviewer),
                    "createdAt": iso_datetime(qc.created_at),
                    "reviewedAt": iso_datetime(qc.reviewed_at),
                    "deadlineAt": iso_datetime(qc.deadline_at),
                    "resultSnapshot": qc.result_snapshot,
                    "media": [photo_data(photo) for photo in qc.photos.all()],
                    "failedItems": [
                        {
                            "id": str(failed.id),
                            "checklistItemId": str(failed.checklist_item_id),
                            "title": failed.checklist_item.title,
                            "reasonCode": failed.reason_code,
                            "reason": failed.reason,
                            "note": failed.note,
                            "reworkRequired": failed.rework_required,
                        }
                        for failed in qc.failed_items.all()
                    ],
                }
                for qc in task.qc_rounds.all()
            ],
            "reworkRounds": [
                {
                    "id": str(rework.id),
                    "round": rework.round_number,
                    "status": rework.status,
                    "sourceQCRoundId": str(rework.source_qc_round_id),
                    "sourceQCRound": rework.source_qc_round.round_number,
                    "failedItemsOnly": rework.failed_items_only,
                    "checklistSnapshot": rework.checklist_snapshot,
                    "startedBy": user_data(rework.started_by),
                    "startedAt": iso_datetime(rework.started_at),
                    "sentToQCAt": iso_datetime(rework.sent_to_qc_at),
                    "completedAt": iso_datetime(rework.completed_at),
                }
                for rework in task.rework_rounds.all()
            ],
            "roomVerifications": [
                {
                    "id": str(verification.id),
                    "method": verification.method,
                    "successful": verification.successful,
                    "failureReason": verification.failure_reason,
                    "serverReference": verification.server_reference,
                    "location": {
                        "latitude": str(verification.latitude),
                        "longitude": str(verification.longitude),
                        "accuracyMeters": str(verification.accuracy_meters),
                    }
                    if verification.latitude is not None and verification.longitude is not None
                    else None,
                    "wifiIdentifier": verification.wifi_identifier,
                    "guestConsentConfirmed": verification.guest_consent_confirmed,
                    "guestConsentNote": verification.guest_consent_note,
                    "verifiedBy": user_data(verification.user),
                    "verifiedAt": iso_datetime(verification.verified_at),
                }
                for verification in task.room_verifications.all()
            ],
            "pauses": [
                {
                    "id": pause.id,
                    "previousStatus": pause.previous_status,
                    "reasonCode": pause.reason_code,
                    "note": pause.note,
                    "excludedFromSLA": pause.excluded_from_sla,
                    "pausedAt": iso_datetime(pause.paused_at),
                    "resumedAt": iso_datetime(pause.resumed_at),
                    "durationSeconds": max(
                        0,
                        int(((pause.resumed_at or timezone.now()) - pause.paused_at).total_seconds()),
                    ),
                }
                for pause in task.pauses.all()
            ],
            "sla": _sla_data(task),
            "timeline": [
                {
                    "fromStatus": event.from_status,
                    "toStatus": event.to_status,
                    "reasonCode": event.reason_code,
                    "note": event.note,
                    "taskVersion": event.task_version,
                    "metadata": event.metadata,
                    "changedBy": user_data(event.changed_by),
                    "changedAt": iso_datetime(event.changed_at),
                }
                for event in task.status_history.all()
            ],
        }
    )
    return data


def _sla_data(task):
    try:
        state = task.sla_state
    except HousekeepingTask.sla_state.RelatedObjectDoesNotExist:
        return None
    return {
        "acceptanceDueAt": iso_datetime(state.acceptance_due_at),
        "startDueAt": iso_datetime(state.start_due_at),
        "completionDueAt": iso_datetime(state.completion_due_at),
        "excludedPauseSeconds": state.excluded_pause_seconds,
        "acceptanceBreachedAt": iso_datetime(state.acceptance_breached_at),
        "startBreachedAt": iso_datetime(state.start_breached_at),
        "completionBreachedAt": iso_datetime(state.completion_breached_at),
        "checkinRiskAt": iso_datetime(state.checkin_risk_at),
    }


def mutation_task_data(task):
    return {
        "taskId": str(task.id),
        "status": task.status,
        "roomStatus": task.room.status,
        "assigneeId": str(task.assignee_id) if task.assignee_id else None,
        "acceptedAt": iso_datetime(task.accepted_at),
        "startedAt": iso_datetime(task.started_at),
        "completedAt": iso_datetime(task.completed_at),
        "progressPercent": task.progress_percent,
        "priority": task.priority,
        "version": task.version,
    }


def supply_request_data(supply):
    return {
        "id": str(supply.id),
        "taskId": str(supply.task_id),
        "taskCode": supply.task.code,
        "room": {"id": str(supply.task.room_id), "code": supply.task.room.code},
        "branch": {"id": str(supply.branch_id), "code": supply.branch.code, "name": supply.branch.name},
        "destination": {
            "id": str(supply.destination_id),
            "code": supply.destination.code,
            "name": supply.destination.name,
        }
        if supply.destination
        else None,
        "requestedBy": user_data(supply.requested_by),
        "priority": supply.priority,
        "note": supply.note,
        "blocksCompletion": supply.blocks_completion,
        "status": supply.status,
        "version": supply.version,
        "requestedAt": iso_datetime(supply.created_at),
        "acknowledgedAt": iso_datetime(supply.acknowledged_at),
        "resolvedBy": user_data(supply.resolved_by),
        "resolvedAt": iso_datetime(supply.resolved_at),
        "resolutionNote": supply.resolution_note,
        "items": [
            {
                "inventoryItemId": item.inventory_item_id,
                "name": item.item_name,
                "quantity": str(item.quantity),
                "unit": item.unit,
            }
            for item in supply.items.all()
        ],
    }


def issue_data(issue):
    return {
        "id": str(issue.id),
        "taskId": str(issue.task_id),
        "taskCode": issue.task.code,
        "room": {"id": str(issue.room_id), "code": issue.room.code, "name": issue.room.name},
        "branch": {
            "id": str(issue.task.branch_id),
            "code": issue.task.branch.code,
            "name": issue.task.branch.name,
        },
        "bookingId": str(issue.booking_id) if issue.booking_id else None,
        "reportedBy": user_data(issue.reported_by),
        "assignedTo": user_data(issue.assigned_to),
        "deviceId": issue.device_id,
        "issueType": issue.issue_type,
        "severity": issue.severity,
        "description": issue.description,
        "blocksRoomReady": issue.blocks_room_ready,
        "status": issue.status,
        "version": issue.version,
        "reportedAt": iso_datetime(issue.created_at),
        "assignedAt": iso_datetime(issue.assigned_at),
        "resolvedBy": user_data(issue.resolved_by),
        "resolvedAt": iso_datetime(issue.resolved_at),
        "resolutionNote": issue.resolution_note,
    }


def notification_data(recipient):
    notification = recipient.notification
    return {
        "recipientId": str(recipient.id),
        "notificationId": str(notification.id),
        "type": notification.notification_type,
        "title": localized_system_text(notification.title),
        "body": localized_system_text(notification.body),
        "branchId": str(notification.branch_id) if notification.branch_id else None,
        "taskId": str(notification.task_id) if notification.task_id else None,
        "objectType": notification.object_type,
        "objectId": notification.object_id,
        "payload": notification.payload,
        "deliveredAt": iso_datetime(recipient.delivered_at),
        "readAt": iso_datetime(recipient.read_at),
        "createdAt": iso_datetime(notification.created_at),
    }
