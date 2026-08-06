import hashlib
import re
from datetime import timedelta

from django.db import migrations
from django.db.models import Max
from django.utils import timezone


TERMINAL_TASK_STATUSES = {"QC_APPROVED", "CANCELLED"}
ACTIVE_ASSIGNMENT_STATUSES = {
    "ACCEPTED",
    "IN_PROGRESS",
    "PAUSED",
    "WAITING_SUPPORT",
    "COMPLETED",
    "WAITING_QC",
    "QC_REJECTED",
}


def _legacy_code(prefix, *values, length=10):
    source = ":".join(str(value or "") for value in values)
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def _membership_role(user_role, can_manage_team):
    if user_role == "housekeeping":
        return "HOUSEKEEPING_LEAD" if can_manage_team else "HOUSEKEEPER"
    if user_role in {"founder", "admin", "manager"}:
        return "MANAGER"
    if user_role == "qc":
        return "QC"
    if user_role == "warehouse":
        return "WAREHOUSE"
    if user_role == "technician":
        return "TECHNICIAN"
    return "VIEWER"


def _checklist_version_number(ChecklistVersion, template_id, label):
    match = re.search(r"(\d+)", label)
    proposed = max(1, int(match.group(1))) if match else 1
    while ChecklistVersion.objects.filter(template_id=template_id, version_number=proposed).exists():
        proposed += 1
    return proposed


def backfill_domain_foundation(apps, schema_editor):
    Branch = apps.get_model("housekeeping", "Branch")
    BranchPolicy = apps.get_model("housekeeping", "BranchHousekeepingPolicy")
    Area = apps.get_model("housekeeping", "Area")
    Team = apps.get_model("housekeeping", "HousekeepingTeam")
    Membership = apps.get_model("housekeeping", "BranchMembership")
    ShiftAssignment = apps.get_model("housekeeping", "ShiftAssignment")
    Room = apps.get_model("housekeeping", "Room")
    Booking = apps.get_model("housekeeping", "Booking")
    ChecklistTemplate = apps.get_model("housekeeping", "ChecklistTemplate")
    ChecklistVersion = apps.get_model("housekeeping", "ChecklistVersion")
    ChecklistDefinition = apps.get_model("housekeeping", "ChecklistItemDefinition")
    Task = apps.get_model("housekeeping", "HousekeepingTask")
    TaskAssignment = apps.get_model("housekeeping", "TaskAssignment")
    ChecklistItem = apps.get_model("housekeeping", "TaskChecklistItem")
    TaskPhoto = apps.get_model("housekeeping", "TaskPhoto")
    Issue = apps.get_model("housekeeping", "IssueTicket")
    QCTask = apps.get_model("housekeeping", "QCTask")
    ReworkRound = apps.get_model("housekeeping", "ReworkRound")
    SupplyLocation = apps.get_model("housekeeping", "SupplyLocation")
    SupplyRequest = apps.get_model("housekeeping", "SupplyRequest")
    SLAPolicy = apps.get_model("housekeeping", "SLAPolicy")
    TaskSLAState = apps.get_model("housekeeping", "TaskSLAState")

    default_teams = {}
    default_sla_policies = {}
    for branch in Branch.objects.all().iterator():
        BranchPolicy.objects.get_or_create(branch_id=branch.id)
        team, _ = Team.objects.get_or_create(
            branch_id=branch.id,
            code="LEGACY-HOUSEKEEPING",
            defaults={"name": "Housekeeping mặc định"},
        )
        default_teams[branch.id] = team
        sla_policy, _ = SLAPolicy.objects.get_or_create(
            branch_id=branch.id,
            name="SLA Housekeeping mặc định",
            task_type="",
            priority="",
            defaults={
                "acceptance_minutes": 5,
                "start_minutes": 15,
                "completion_minutes": 45,
                "checkin_risk_buffer_minutes": 15,
                "escalation_minutes": [5, 15, 30],
            },
        )
        default_sla_policies[branch.id] = sla_policy
        SupplyLocation.objects.get_or_create(
            branch_id=branch.id,
            code="DEFAULT",
            defaults={"name": "Kho mặc định"},
        )

    area_cache = {}

    def ensure_area(branch_id, area_name, floor_label=""):
        normalized_name = str(area_name or "").strip()
        if not normalized_name:
            return None
        key = (branch_id, normalized_name.casefold())
        if key in area_cache:
            return area_cache[key]
        code = _legacy_code("AREA", branch_id, normalized_name)
        area, _ = Area.objects.get_or_create(
            branch_id=branch_id,
            code=code,
            defaults={"name": normalized_name, "floor_label": str(floor_label or "")[:80]},
        )
        area_cache[key] = area
        return area

    for room in Room.objects.all().iterator():
        area = ensure_area(room.branch_id, room.area, room.floor)
        if area is not None and room.area_ref_id != area.id:
            room.area_ref_id = area.id
            room.save(update_fields=["area_ref"])

    for membership in Membership.objects.select_related("user").all().iterator():
        role = _membership_role(membership.user.role, membership.can_manage_team)
        team = default_teams.get(membership.branch_id)
        membership.membership_role = role
        if role in {"HOUSEKEEPER", "HOUSEKEEPING_LEAD"}:
            membership.team_id = team.id
        membership.save(update_fields=["membership_role", "team"])
        area = ensure_area(membership.branch_id, membership.area)
        if area is not None:
            membership.areas.add(area)
            if team is not None:
                team.areas.add(area)
        if role == "HOUSEKEEPING_LEAD" and team is not None and team.leader_id is None:
            team.leader_id = membership.user_id
            team.save(update_fields=["leader"])

    for task in Task.objects.select_related("room").all().iterator():
        update_fields = []
        if task.room.area_ref_id and task.area_id != task.room.area_ref_id:
            task.area_id = task.room.area_ref_id
            update_fields.append("area")
        team = default_teams.get(task.branch_id)
        if task.assignee_id and team is not None and task.team_id is None:
            task.team_id = team.id
            update_fields.append("team")
        if task.created_by_id and task.assigned_by_id is None:
            task.assigned_by_id = task.created_by_id
            update_fields.append("assigned_by")
        if task.due_at and task.scheduled_start_at and task.standard_duration_minutes is None:
            seconds = max(60, int((task.due_at - task.scheduled_start_at).total_seconds()))
            task.standard_duration_minutes = max(1, seconds // 60)
            update_fields.append("standard_duration_minutes")
        if task.progress_percent and task.last_progress_at is None:
            task.last_progress_at = task.updated_at
            task.updated_by_id = task.assignee_id
            update_fields.extend(["last_progress_at", "updated_by"])
        if task.rework_count:
            task.current_rework_round = task.rework_count
            if task.rework_started_at is None:
                task.rework_started_at = task.started_at
            update_fields.extend(["current_rework_round", "rework_started_at"])

        policy = default_sla_policies.get(task.branch_id)
        if policy is not None:
            if task.acceptance_due_at is None:
                task.acceptance_due_at = task.created_at + timedelta(minutes=policy.acceptance_minutes)
                update_fields.append("acceptance_due_at")
            if task.start_due_at is None:
                task.start_due_at = task.created_at + timedelta(minutes=policy.start_minutes)
                update_fields.append("start_due_at")

        booking_code = str(task.booking_code or "").strip()
        if booking_code and task.booking_id is None:
            booking, _ = Booking.objects.get_or_create(
                branch_id=task.branch_id,
                code=booking_code,
                defaults={
                    "room_id": task.room_id,
                    "checkin_at": task.next_checkin_at,
                    "special_requests": task.special_request,
                },
            )
            task.booking_id = booking.id
            update_fields.append("booking")

        template_code = f"LEGACY-{task.task_type}"[:80]
        template, _ = ChecklistTemplate.objects.get_or_create(
            branch_id=task.branch_id,
            code=template_code,
            defaults={
                "name": f"Checklist legacy {task.task_type}",
                "task_type": task.task_type,
            },
        )
        version_label = str(task.checklist_version or "v1")[:30]
        checklist_version = ChecklistVersion.objects.filter(
            template_id=template.id,
            version_label=version_label,
        ).first()
        if checklist_version is None:
            checklist_version = ChecklistVersion.objects.create(
                template_id=template.id,
                version_number=_checklist_version_number(ChecklistVersion, template.id, version_label),
                version_label=version_label,
                status="PUBLISHED",
                published_at=task.created_at or timezone.now(),
                created_by_id=task.created_by_id,
                policy_snapshot={"legacy_backfill": True},
            )
        if task.checklist_template_version_id != checklist_version.id:
            task.checklist_template_version_id = checklist_version.id
            update_fields.append("checklist_template_version")

        if update_fields:
            task.save(update_fields=list(dict.fromkeys(update_fields)))

        for item in ChecklistItem.objects.filter(task_id=task.id).iterator():
            definition, _ = ChecklistDefinition.objects.get_or_create(
                version_id=checklist_version.id,
                key=item.definition_key,
                defaults={
                    "group_name": item.group_name,
                    "title": item.title,
                    "item_type": item.item_type,
                    "is_required": item.is_required,
                    "required_photo_count": 1 if item.requires_photo else 0,
                    "options": item.options_snapshot,
                    "validation_rules": item.validation_snapshot,
                    "sort_order": item.sort_order,
                },
            )
            if item.definition_id != definition.id:
                item.definition_id = definition.id
                item.save(update_fields=["definition"])

        if task.assignee_id:
            is_current = task.status not in TERMINAL_TASK_STATUSES
            assignment_status = "ENDED" if not is_current else (
                "ACCEPTED" if task.status in ACTIVE_ASSIGNMENT_STATUSES or task.accepted_at else "PENDING"
            )
            assignment, _ = TaskAssignment.objects.get_or_create(
                task_id=task.id,
                assignee_id=task.assignee_id,
                assigned_at=task.accepted_at or task.created_at,
                defaults={
                    "assigned_by_id": task.assigned_by_id,
                    "shift_id": task.shift_id,
                    "team_id": task.team_id,
                    "status": assignment_status,
                    "is_current": is_current,
                    "accepted_at": task.accepted_at,
                    "ended_at": task.completed_at if not is_current else None,
                    "note": "Backfill từ assignment hiện có.",
                },
            )
            if task.shift_id:
                shift_assignment, _ = ShiftAssignment.objects.get_or_create(
                    user_id=task.assignee_id,
                    shift_id=task.shift_id,
                    defaults={
                        "team_id": task.team_id,
                        "assigned_by_id": task.assigned_by_id,
                    },
                )
                if task.area_id:
                    shift_assignment.areas.add(task.area_id)

        if policy is not None:
            TaskSLAState.objects.get_or_create(
                task_id=task.id,
                defaults={
                    "policy_id": policy.id,
                    "policy_snapshot": {
                        "acceptanceMinutes": policy.acceptance_minutes,
                        "startMinutes": policy.start_minutes,
                        "completionMinutes": policy.completion_minutes,
                        "checkinRiskBufferMinutes": policy.checkin_risk_buffer_minutes,
                        "legacyBackfill": True,
                    },
                    "acceptance_due_at": task.acceptance_due_at,
                    "start_due_at": task.start_due_at,
                    "completion_due_at": task.due_at,
                    "legacy_backfill": True,
                },
            )

    for issue in Issue.objects.select_related("task").all().iterator():
        if issue.booking_id is None and issue.task.booking_id:
            issue.booking_id = issue.task.booking_id
            issue.save(update_fields=["booking"])

    for photo in TaskPhoto.objects.select_related("task").all().iterator():
        update_fields = []
        if photo.room_id is None:
            photo.room_id = photo.task.room_id
            update_fields.append("room")
        if photo.captured_at is None:
            photo.captured_at = photo.created_at
            update_fields.append("captured_at")
        photo.sync_status = "SYNCED" if photo.synced else "PENDING"
        update_fields.append("sync_status")
        photo.save(update_fields=list(dict.fromkeys(update_fields)))

    for request in SupplyRequest.objects.all().iterator():
        warehouse_name = str(request.warehouse or "").strip()
        if warehouse_name:
            code = _legacy_code("WAREHOUSE", request.branch_id, warehouse_name, length=8)
            destination, _ = SupplyLocation.objects.get_or_create(
                branch_id=request.branch_id,
                code=code,
                defaults={"name": warehouse_name},
            )
        else:
            destination = SupplyLocation.objects.get(branch_id=request.branch_id, code="DEFAULT")
        if request.destination_id != destination.id:
            request.destination_id = destination.id
            request.save(update_fields=["destination"])

    for qc_round in QCTask.objects.select_related("task").all().iterator():
        if not qc_round.checklist_snapshot:
            qc_round.checklist_snapshot = list(
                ChecklistItem.objects.filter(task_id=qc_round.task_id)
                .order_by("sort_order", "id")
                .values(
                    "definition_key",
                    "group_name",
                    "title",
                    "item_type",
                    "is_required",
                    "status",
                    "value",
                    "note",
                )
            )
        if qc_round.status != "PENDING" and not qc_round.result_snapshot:
            qc_round.result_snapshot = {
                "status": qc_round.status,
                "reason": qc_round.reason,
                "note": qc_round.note,
                "legacyBackfill": True,
            }
        qc_round.save(update_fields=["checklist_snapshot", "result_snapshot"])

    for task in Task.objects.filter(rework_count__gt=0).iterator():
        rejected_rounds = list(
            QCTask.objects.filter(task_id=task.id, status="REJECTED").order_by("round_number")
        )
        for round_number in range(1, task.rework_count + 1):
            if not rejected_rounds:
                break
            source_round = rejected_rounds[min(round_number - 1, len(rejected_rounds) - 1)]
            status = "IN_PROGRESS" if task.status == "IN_PROGRESS" else (
                "SENT_TO_QC" if task.status in {"WAITING_QC", "QC_APPROVED"} else "PENDING"
            )
            ReworkRound.objects.get_or_create(
                task_id=task.id,
                round_number=round_number,
                defaults={
                    "source_qc_round_id": source_round.id,
                    "status": status,
                    "failed_items_only": True,
                    "checklist_snapshot": source_round.checklist_snapshot,
                    "started_by_id": task.assignee_id,
                    "started_at": task.rework_started_at or task.started_at,
                    "sent_to_qc_at": task.completed_at if status == "SENT_TO_QC" else None,
                },
            )


def reverse_domain_backfill(apps, schema_editor):
    apps.get_model("housekeeping", "IssueTicket").objects.update(booking=None)
    apps.get_model("housekeeping", "TaskPhoto").objects.update(
        room=None,
        captured_at=None,
        sync_status="SYNCED",
    )
    apps.get_model("housekeeping", "SupplyRequest").objects.update(destination=None)
    apps.get_model("housekeeping", "TaskChecklistItem").objects.update(definition=None)
    apps.get_model("housekeeping", "HousekeepingTask").objects.update(
        booking=None,
        area=None,
        team=None,
        assigned_by=None,
        checklist_template_version=None,
        acceptance_due_at=None,
        start_due_at=None,
        standard_duration_minutes=None,
        last_progress_at=None,
        updated_by=None,
        rework_started_at=None,
        current_rework_round=0,
    )
    Membership = apps.get_model("housekeeping", "BranchMembership")
    for membership in Membership.objects.all().iterator():
        membership.areas.clear()
        membership.skills.clear()
    Membership.objects.update(team=None, membership_role="HOUSEKEEPER")
    apps.get_model("housekeeping", "ReworkRound").objects.all().delete()
    apps.get_model("housekeeping", "TaskSLAState").objects.all().delete()
    apps.get_model("housekeeping", "TaskAssignment").objects.all().delete()
    apps.get_model("housekeeping", "ShiftAssignment").objects.all().delete()
    apps.get_model("housekeeping", "Booking").objects.all().delete()
    apps.get_model("housekeeping", "ChecklistItemDefinition").objects.all().delete()
    apps.get_model("housekeeping", "ChecklistVersion").objects.all().delete()
    apps.get_model("housekeeping", "ChecklistTemplate").objects.all().delete()
    apps.get_model("housekeeping", "SLAPolicy").objects.all().delete()
    apps.get_model("housekeeping", "SupplyLocation").objects.all().delete()
    apps.get_model("housekeeping", "HousekeepingTeam").objects.all().delete()
    apps.get_model("housekeeping", "Area").objects.all().delete()
    apps.get_model("housekeeping", "BranchHousekeepingPolicy").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("housekeeping", "0002_domain_foundation")]

    operations = [
        migrations.RunPython(backfill_domain_foundation, reverse_domain_backfill),
    ]
