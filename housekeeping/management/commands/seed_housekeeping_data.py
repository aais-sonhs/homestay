import hashlib
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Area,
    Booking,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    HousekeepingTeam,
    HousekeepingTask,
    QCTask,
    Room,
    Shift,
    ShiftAssignment,
    SLAPolicy,
    SupplyLocation,
    TaskAssignment,
    TaskChecklistItem,
    TaskSLAState,
    TaskStatusHistory,
)


CHECKLIST = (
    ("entrance", "Khu vực chung", "Kiểm tra cửa, khóa và thẻ phòng", False),
    ("bed", "Phòng ngủ", "Thay ga, gối và sắp xếp giường", False),
    ("bathroom", "Phòng tắm", "Vệ sinh phòng tắm và bổ sung khăn", True),
    ("amenities", "Tiện nghi", "Bổ sung nước và đồ dùng tiện nghi", False),
    ("final", "Kiểm tra cuối", "Kiểm tra mùi, ánh sáng và điều hòa", False),
)


class Command(BaseCommand):
    help = "Tạo chi nhánh, ca, phòng và công việc buồng phòng mẫu cho ngày hiện tại."

    def handle(self, *args, **options):
        try:
            founder = User.objects.get(username="admin")
            manager = User.objects.get(username="manager")
            housekeeper = User.objects.get(username="housekeeping")
            qc = User.objects.get(username="qc")
            warehouse = User.objects.get(username="warehouse")
            technician = User.objects.get(username="technician")
            customer_service = User.objects.get(username="customer_service")
            housekeeping_lead = User.objects.get(username="housekeeping_lead")
            viewer = User.objects.get(username="viewer")
        except User.DoesNotExist as error:
            raise CommandError("Hãy chạy lệnh tạo dữ liệu tài khoản mẫu trước.") from error

        dalat, _ = Branch.objects.get_or_create(
            code="DALAT",
            defaults={"name": "Bliss Home Đà Lạt", "address": "Đà Lạt, Lâm Đồng"},
        )
        hcm, _ = Branch.objects.get_or_create(
            code="HCM",
            defaults={"name": "Bliss Home TP. Hồ Chí Minh", "address": "TP. Hồ Chí Minh"},
        )
        for branch in (dalat, hcm):
            BranchHousekeepingPolicy.objects.get_or_create(branch=branch)
            SupplyLocation.objects.get_or_create(
                branch=branch,
                code="DEFAULT",
                defaults={"name": "Kho mặc định"},
            )
            SLAPolicy.objects.get_or_create(
                branch=branch,
                name="Thời hạn buồng phòng mặc định",
                task_type="",
                priority="",
            )
        teams = {}
        for branch in (dalat, hcm):
            teams[branch.id], _ = HousekeepingTeam.objects.get_or_create(
                branch=branch,
                code="HOUSEKEEPING",
                defaults={"name": "Đội buồng phòng"},
            )

        role_by_user = {
            manager.id: BranchMembership.MembershipRole.MANAGER,
            qc.id: BranchMembership.MembershipRole.QC,
            warehouse.id: BranchMembership.MembershipRole.WAREHOUSE,
            technician.id: BranchMembership.MembershipRole.TECHNICIAN,
            customer_service.id: BranchMembership.MembershipRole.VIEWER,
            housekeeping_lead.id: BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
            viewer.id: BranchMembership.MembershipRole.VIEWER,
        }
        for user in (
            manager,
            qc,
            warehouse,
            technician,
            customer_service,
            housekeeping_lead,
            viewer,
        ):
            for branch in (dalat, hcm):
                is_team_manager = user in {manager, housekeeping_lead}
                membership, _ = BranchMembership.objects.get_or_create(
                    user=user,
                    branch=branch,
                    defaults={
                        "can_manage_team": is_team_manager,
                        "membership_role": role_by_user[user.id],
                        "team": teams[branch.id] if user == housekeeping_lead else None,
                    },
                )
                membership.membership_role = role_by_user[user.id]
                membership.can_manage_team = is_team_manager
                membership.team = teams[branch.id] if user == housekeeping_lead else None
                membership.is_active = True
                membership.save(
                    update_fields=["membership_role", "can_manage_team", "team", "is_active"]
                )
        housekeeper_membership, _ = BranchMembership.objects.get_or_create(
            user=housekeeper,
            branch=dalat,
            defaults={
                "area": "Khu A",
                "membership_role": BranchMembership.MembershipRole.HOUSEKEEPER,
                "team": teams[dalat.id],
            },
        )
        housekeeper_membership.membership_role = BranchMembership.MembershipRole.HOUSEKEEPER
        housekeeper_membership.team = teams[dalat.id]
        housekeeper_membership.save(update_fields=["membership_role", "team"])

        today = timezone.localdate()
        local_tz = timezone.get_current_timezone()
        shift_start = timezone.make_aware(datetime.combine(today, time(6, 0)), local_tz)
        shift_end = timezone.make_aware(datetime.combine(today, time(23, 59)), local_tz)
        shift, _ = Shift.objects.get_or_create(
            branch=dalat,
            code="SHIFT_DAY",
            starts_at=shift_start,
            defaults={"name": "Ca trong ngày", "ends_at": shift_end},
        )
        Shift.objects.filter(pk=shift.pk).update(ends_at=shift_end, is_active=True)
        hcm_shift, _ = Shift.objects.get_or_create(
            branch=hcm,
            code="SHIFT_DAY",
            starts_at=shift_start,
            defaults={"name": "Ca trong ngày", "ends_at": shift_end},
        )
        Shift.objects.filter(pk=hcm_shift.pk).update(ends_at=shift_end, is_active=True)

        room_specs = (
            (dalat, "A101", "Phòng A101", "Tầng 1", "Khu A"),
            (dalat, "A102", "Phòng A102", "Tầng 1", "Khu A"),
            (dalat, "A201", "Phòng A201", "Tầng 2", "Khu A"),
            (dalat, "B301", "Phòng B301", "Tầng 3", "Khu B"),
            (dalat, "B302", "Phòng B302", "Tầng 3", "Khu B"),
            (hcm, "S101", "Phòng hạng sang S101", "Tầng 1", "Khu S"),
        )
        rooms = {}
        areas = {}
        for branch, code, name, floor, area in room_specs:
            area_code = "AREA-" + hashlib.sha1(f"{branch.id}:{area}".encode("utf-8")).hexdigest()[:10].upper()
            area_object, _ = Area.objects.get_or_create(
                branch=branch,
                code=area_code,
                defaults={"name": area, "floor_label": floor},
            )
            areas[(branch.id, area)] = area_object
            room, _ = Room.objects.get_or_create(
                branch=branch,
                code=code,
                defaults={
                    "name": name,
                    "floor": floor,
                    "area": area,
                    "area_ref": area_object,
                    "room_type": "Cao cấp",
                    "status": Room.Status.WAITING_CLEANING,
                },
            )
            if room.area_ref_id != area_object.id:
                room.area_ref = area_object
                room.save(update_fields=["area_ref"])
            rooms[code] = room

        dalat_area_a = areas[(dalat.id, "Khu A")]
        housekeeper_membership.areas.add(dalat_area_a)
        teams[dalat.id].areas.add(*[area for (branch_id, _), area in areas.items() if branch_id == dalat.id])
        teams[hcm.id].areas.add(*[area for (branch_id, _), area in areas.items() if branch_id == hcm.id])

        now = timezone.now()
        day_key = today.strftime("%Y%m%d")
        task_specs = (
            {
                "code": f"HK-{day_key}-001",
                "room": rooms["A101"],
                "task_type": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
                "priority": HousekeepingTask.Priority.URGENT,
                "status": HousekeepingTask.Status.UNASSIGNED,
                "assignee": None,
                "due_at": now - timedelta(minutes=15),
                "next_checkin_at": now + timedelta(hours=1),
                "special_request": "Ưu tiên phòng có khách sắp nhận phòng.",
            },
            {
                "code": f"HK-{day_key}-002",
                "room": rooms["A102"],
                "task_type": HousekeepingTask.TaskType.CHECKIN_PREPARATION,
                "priority": HousekeepingTask.Priority.HIGH,
                "status": HousekeepingTask.Status.PENDING_ACCEPTANCE,
                "assignee": housekeeper,
                "due_at": now + timedelta(minutes=45),
                "next_checkin_at": now + timedelta(hours=2),
                "special_request": "Chuẩn bị thêm nôi em bé.",
            },
            {
                "code": f"HK-{day_key}-003",
                "room": rooms["A201"],
                "task_type": HousekeepingTask.TaskType.DEEP_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.ACCEPTED,
                "assignee": housekeeper,
                "due_at": now + timedelta(hours=2),
                "next_checkin_at": None,
                "special_request": "",
            },
            {
                "code": f"HK-{day_key}-004",
                "room": rooms["B301"],
                "task_type": HousekeepingTask.TaskType.QC_REWORK,
                "priority": HousekeepingTask.Priority.HIGH,
                "status": HousekeepingTask.Status.QC_REJECTED,
                "assignee": housekeeper,
                "due_at": now + timedelta(minutes=30),
                "next_checkin_at": now + timedelta(hours=3),
                "special_request": "",
            },
            {
                "code": f"HK-{day_key}-005",
                "room": rooms["B302"],
                "task_type": HousekeepingTask.TaskType.STAYOVER_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.WAITING_QC,
                "assignee": housekeeper,
                "due_at": now + timedelta(hours=3),
                "next_checkin_at": None,
                "special_request": "Khách yêu cầu thay toàn bộ khăn.",
            },
            {
                "code": f"HK-{day_key}-HCM-001",
                "room": rooms["S101"],
                "task_type": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.UNASSIGNED,
                "assignee": None,
                "due_at": now + timedelta(hours=1),
                "next_checkin_at": None,
                "special_request": "",
            },
        )

        created_count = 0
        for spec in task_specs:
            branch = spec["room"].branch
            task_shift = shift if branch == dalat else hcm_shift
            booking_code = f"BK-{spec['room'].code}-{day_key}"
            booking, _ = Booking.objects.get_or_create(
                branch=branch,
                code=booking_code,
                defaults={
                    "room": spec["room"],
                    "checkin_at": spec["next_checkin_at"],
                    "special_requests": spec["special_request"],
                },
            )
            template, _ = ChecklistTemplate.objects.get_or_create(
                branch=branch,
                code=f"{spec['task_type']}-DEFAULT",
                defaults={
                    "name": (
                        "Danh sách kiểm tra "
                        f"{dict(HousekeepingTask.TaskType.choices)[spec['task_type']]}"
                    ),
                    "task_type": spec["task_type"],
                },
            )
            checklist_version, _ = ChecklistVersion.objects.get_or_create(
                template=template,
                version_number=1,
                defaults={
                    "version_label": "v1",
                    "status": ChecklistVersion.Status.PUBLISHED,
                    "published_at": now,
                    "created_by": founder,
                },
            )
            task, created = HousekeepingTask.objects.get_or_create(
                code=spec["code"],
                defaults={
                    "branch": branch,
                    "room": spec["room"],
                    "booking_code": booking_code,
                    "booking": booking,
                    "task_type": spec["task_type"],
                    "priority": spec["priority"],
                    "status": spec["status"],
                    "assignee": spec["assignee"],
                    "assigned_by": founder if spec["assignee"] else None,
                    "shift": task_shift,
                    "team": teams[branch.id],
                    "area": spec["room"].area_ref,
                    "checklist_template_version": checklist_version,
                    "scheduled_start_at": now - timedelta(minutes=30),
                    "acceptance_due_at": now - timedelta(minutes=25),
                    "start_due_at": now - timedelta(minutes=15),
                    "due_at": spec["due_at"],
                    "standard_duration_minutes": 45,
                    "next_checkin_at": spec["next_checkin_at"],
                    "accepted_at": now - timedelta(minutes=10) if spec["status"] == HousekeepingTask.Status.ACCEPTED else None,
                    "completed_at": now - timedelta(minutes=5) if spec["status"] == HousekeepingTask.Status.WAITING_QC else None,
                    "progress_percent": 100 if spec["status"] == HousekeepingTask.Status.WAITING_QC else 0,
                    "special_request": spec["special_request"],
                    "created_by": founder,
                },
            )
            task.booking = booking
            task.area = spec["room"].area_ref
            task.team = teams[branch.id]
            task.checklist_template_version = checklist_version
            task.assigned_by = founder if task.assignee_id else None
            task.standard_duration_minutes = task.standard_duration_minutes or 45
            task.save(
                update_fields=[
                    "booking",
                    "area",
                    "team",
                    "checklist_template_version",
                    "assigned_by",
                    "standard_duration_minutes",
                ]
            )
            if task.assignee_id:
                assignment, _ = TaskAssignment.objects.get_or_create(
                    task=task,
                    assignee=task.assignee,
                    assigned_at=task.accepted_at or task.created_at,
                    defaults={
                        "assigned_by": founder,
                        "shift": task_shift,
                        "team": teams[branch.id],
                        "status": (
                            TaskAssignment.Status.PENDING
                            if task.status == HousekeepingTask.Status.PENDING_ACCEPTANCE
                            else TaskAssignment.Status.ACCEPTED
                        ),
                        "accepted_at": task.accepted_at,
                    },
                )
                shift_assignment, _ = ShiftAssignment.objects.get_or_create(
                    user=task.assignee,
                    shift=task_shift,
                    defaults={"team": teams[branch.id], "assigned_by": founder},
                )
                if task.area_id:
                    shift_assignment.areas.add(task.area_id)
            sla_policy = SLAPolicy.objects.get(
                branch=branch,
                name="Thời hạn buồng phòng mặc định",
                task_type="",
                priority="",
            )
            TaskSLAState.objects.get_or_create(
                task=task,
                defaults={
                    "policy": sla_policy,
                    "policy_snapshot": {
                        "acceptanceMinutes": sla_policy.acceptance_minutes,
                        "startMinutes": sla_policy.start_minutes,
                        "completionMinutes": sla_policy.completion_minutes,
                    },
                    "acceptance_due_at": task.acceptance_due_at,
                    "start_due_at": task.start_due_at,
                    "completion_due_at": task.due_at,
                },
            )
            if created:
                created_count += 1
                TaskStatusHistory.objects.create(
                    task=task,
                    from_status="",
                    to_status=task.status,
                    changed_by=founder,
                    note="Dữ liệu mẫu được tạo tự động.",
                )
                task.room.status = {
                    HousekeepingTask.Status.QC_REJECTED: Room.Status.REWORK_REQUIRED,
                    HousekeepingTask.Status.WAITING_QC: Room.Status.WAITING_QC,
                }.get(task.status, Room.Status.WAITING_CLEANING)
                task.room.save(update_fields=["status"])
            for order, (key, group, title, photo_required) in enumerate(CHECKLIST, start=1):
                definition, _ = ChecklistItemDefinition.objects.get_or_create(
                    version=checklist_version,
                    key=key,
                    defaults={
                        "group_name": group,
                        "title": title,
                        "is_required": True,
                        "required_photo_count": 1 if photo_required else 0,
                        "sort_order": order,
                    },
                )
                item, _ = TaskChecklistItem.objects.get_or_create(
                    task=task,
                    definition_key=key,
                    defaults={
                        "definition": definition,
                        "group_name": group,
                        "title": title,
                        "is_required": True,
                        "requires_photo": photo_required,
                        "sort_order": order,
                    },
                )
                if item.definition_id != definition.id:
                    item.definition = definition
                    item.save(update_fields=["definition"])
                if created and task.status == HousekeepingTask.Status.WAITING_QC:
                    item.status = TaskChecklistItem.Status.COMPLETED
                    item.completed_by = housekeeper
                    item.completed_at = now - timedelta(minutes=10)
                    item.save(update_fields=["status", "completed_by", "completed_at"])
            if created and task.status == HousekeepingTask.Status.QC_REJECTED:
                QCTask.objects.create(
                    task=task,
                    round_number=1,
                    status=QCTask.Status.REJECTED,
                    reviewer=qc,
                    reason="Gương phòng tắm còn vệt nước.",
                    note="Lau lại gương và chụp ảnh xác nhận.",
                    reviewed_at=now - timedelta(minutes=15),
                )
            if created and task.status == HousekeepingTask.Status.WAITING_QC:
                QCTask.objects.create(task=task, round_number=1)

        self.stdout.write(
            self.style.SUCCESS(
                f"Dữ liệu buồng phòng đã sẵn sàng: {Branch.objects.count()} chi nhánh, "
                f"{Room.objects.count()} phòng, tạo mới {created_count} công việc cho {today:%d/%m/%Y}."
            )
        )
