from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    HousekeepingTask,
    Notification,
    NotificationRecipient,
    SLAPolicy,
    TaskAssignment,
    TaskChecklistItem,
    TaskSLAState,
    TaskStatusHistory,
)
from organizations.models import (
    Area,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    HousekeepingTeam,
    Room,
    Shift,
    ShiftAssignment,
)


CHECKLIST_ITEMS = (
    ("entrance", "Khu vực chung", "Kiểm tra cửa, khóa và thẻ phòng"),
    ("bed", "Phòng ngủ", "Thay ga, gối và sắp xếp giường"),
    ("bathroom", "Phòng tắm", "Vệ sinh phòng tắm và bổ sung khăn"),
    ("amenities", "Tiện nghi", "Bổ sung nước và đồ dùng tiện nghi"),
    ("final", "Kiểm tra cuối", "Kiểm tra mùi, ánh sáng và điều hòa"),
)


class Command(BaseCommand):
    help = "Tạo bộ dữ liệu đủ trạng thái để kiểm tra giao diện app tạp vụ."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="tapvu1",
            help="Tên đăng nhập của tài khoản tạp vụ nhận dữ liệu demo.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"].strip()
        try:
            worker = User.objects.get(username__iexact=username)
        except User.DoesNotExist as error:
            raise CommandError(f"Không tìm thấy tài khoản '{username}'.") from error
        except User.MultipleObjectsReturned as error:
            raise CommandError(f"Có nhiều tài khoản trùng tên '{username}'.") from error

        if not worker.is_active or worker.is_deleted:
            raise CommandError(f"Tài khoản '{username}' đang bị khóa hoặc đã xóa.")
        if worker.role != User.Role.HOUSEKEEPING:
            raise CommandError(f"Tài khoản '{username}' không có vai trò tạp vụ.")

        source_membership = (
            BranchMembership.objects.select_related("branch", "branch__owner")
            .filter(user=worker, is_active=True, branch__is_active=True)
            .order_by("branch__code")
            .first()
        )
        if source_membership is None:
            raise CommandError(f"Tài khoản '{username}' chưa thuộc cơ sở đang hoạt động nào.")

        now = timezone.now()
        today = timezone.localdate()
        local_tz = timezone.get_current_timezone()
        day_start = timezone.make_aware(datetime.combine(today, time.min), local_tz)
        day_end = timezone.make_aware(datetime.combine(today, time.max), local_tz)
        scheduled_at = max(day_start + timedelta(minutes=1), now - timedelta(minutes=15))

        branch, _ = Branch.objects.get_or_create(
            code="APP-DEMO",
            defaults={
                "name": "Cơ sở Demo App Tạp vụ",
                "address": "Dữ liệu riêng phục vụ kiểm tra giao diện app",
                "owner": source_membership.branch.owner,
            },
        )
        branch.name = "Cơ sở Demo App Tạp vụ"
        branch.address = "Dữ liệu riêng phục vụ kiểm tra giao diện app"
        branch.is_active = True
        branch.save(update_fields=["name", "address", "is_active"])
        BranchHousekeepingPolicy.objects.update_or_create(
            branch=branch,
            defaults={
                "allow_work_outside_shift": False,
                "require_guest_consent": False,
                "require_qr_verification": False,
                "require_gps_verification": False,
                "require_wifi_verification": False,
                "require_camera_verification": False,
                "block_completion_with_pending_sync": False,
                "block_completion_with_pending_supply": False,
            },
        )

        area, _ = Area.objects.update_or_create(
            branch=branch,
            code="APP-FLOORS",
            defaults={"name": "Khu phòng demo", "floor_label": "Tầng 1-3", "is_active": True},
        )
        team, _ = HousekeepingTeam.objects.update_or_create(
            branch=branch,
            code="APP-HK",
            defaults={"name": "Đội tạp vụ Demo App", "is_active": True},
        )
        team.areas.add(area)

        membership, _ = BranchMembership.objects.update_or_create(
            user=worker,
            branch=branch,
            defaults={
                "is_active": True,
                "can_work_outside_shift": False,
                "can_manage_team": False,
                "area": area.name,
                "membership_role": BranchMembership.MembershipRole.HOUSEKEEPER,
                "team": team,
            },
        )
        membership.areas.add(area)

        shift, _ = Shift.objects.update_or_create(
            branch=branch,
            code="APP-DAY",
            starts_at=day_start,
            defaults={
                "name": "Ca demo hôm nay",
                "ends_at": day_end,
                "is_active": True,
            },
        )
        shift_assignment, _ = ShiftAssignment.objects.update_or_create(
            user=worker,
            shift=shift,
            defaults={
                "team": team,
                "assigned_by": source_membership.branch.owner,
                "is_overtime": False,
                "is_active": True,
            },
        )
        shift_assignment.areas.add(area)

        checklist_version, definitions = self._checklist(
            branch=branch,
            creator=source_membership.branch.owner,
            now=now,
        )
        sla_policy, _ = SLAPolicy.objects.update_or_create(
            branch=branch,
            name="SLA demo app tạp vụ",
            task_type="",
            priority="",
            defaults={
                "acceptance_minutes": 5,
                "start_minutes": 10,
                "completion_minutes": 45,
                "checkin_risk_buffer_minutes": 20,
                "escalation_minutes": [5, 15, 30],
                "is_active": True,
            },
        )

        specs = self._task_specs(now)
        tasks = {}
        created_count = 0
        for index, spec in enumerate(specs, start=1):
            room, _ = Room.objects.update_or_create(
                branch=branch,
                code=spec["room"],
                defaults={
                    "name": f"Phòng {spec['room']}",
                    "floor": spec["floor"],
                    "area": area.name,
                    "area_ref": area,
                    "room_type": "Căn hộ tiêu chuẩn",
                    "status": spec["room_status"],
                    "is_guest_occupied": spec["booking_status"] == Booking.Status.CHECKED_IN,
                    "is_locked": False,
                    "operational_note": spec["room_note"],
                },
            )
            booking_code = f"APP-BK-{index:02d}"
            booking, _ = Booking.objects.update_or_create(
                branch=branch,
                code=booking_code,
                defaults={
                    "room": room,
                    "status": spec["booking_status"],
                    "checkin_at": spec["checkin_at"],
                    "checkout_at": spec["checkout_at"],
                    "guest_name": spec["guest_name"],
                    "guest_count": spec["guest_count"],
                    "special_requests": spec["special_request"],
                    "source": Booking.Source.MANUAL_SALES,
                    "created_by": source_membership.branch.owner,
                    "updated_by": source_membership.branch.owner,
                },
            )

            accepted_at = (
                now - timedelta(minutes=35)
                if spec["status"]
                not in {
                    HousekeepingTask.Status.ASSIGNED,
                    HousekeepingTask.Status.PENDING_ACCEPTANCE,
                }
                else None
            )
            started_at = (
                now - timedelta(minutes=25)
                if spec["status"]
                in {
                    HousekeepingTask.Status.IN_PROGRESS,
                    HousekeepingTask.Status.PAUSED,
                    HousekeepingTask.Status.COMPLETED,
                    HousekeepingTask.Status.WAITING_QC,
                }
                else None
            )
            completed_at = (
                now - timedelta(minutes=8 + index)
                if spec["status"]
                in {HousekeepingTask.Status.COMPLETED, HousekeepingTask.Status.WAITING_QC}
                else None
            )
            task_defaults = {
                "branch": branch,
                "room": room,
                "booking_code": booking.code,
                "booking": booking,
                "task_type": spec["task_type"],
                "priority": spec["priority"],
                "status": spec["status"],
                "assignee": worker,
                "assigned_by": source_membership.branch.owner,
                "shift": shift,
                "team": team,
                "area": area,
                "checklist_version": "v1",
                "checklist_template_version": checklist_version,
                "scheduled_start_at": scheduled_at + timedelta(minutes=index),
                "acceptance_due_at": scheduled_at + timedelta(minutes=5),
                "start_due_at": scheduled_at + timedelta(minutes=10),
                "due_at": spec["due_at"],
                "standard_duration_minutes": 45,
                "next_checkin_at": spec["next_checkin_at"],
                "accepted_at": accepted_at,
                "started_at": started_at,
                "completed_at": completed_at,
                "progress_percent": spec["progress"],
                "estimated_income": spec["estimated_income"],
                "last_progress_at": started_at,
                "updated_by": worker,
                "pause_reason": spec["pause_reason"],
                "requires_qc": True,
                "guest_in_room": spec["booking_status"] == Booking.Status.CHECKED_IN,
                "special_request": spec["special_request"],
                "special_request_items": spec["special_request_items"],
                "note": spec["note"],
                "created_by": source_membership.branch.owner,
            }
            task, created = HousekeepingTask.objects.update_or_create(
                code=f"APP-DEMO-{index:02d}",
                defaults=task_defaults,
            )
            created_count += int(created)
            tasks[spec["room"]] = task

            assignment = TaskAssignment.objects.filter(task=task, assignee=worker).order_by("assigned_at").first()
            if assignment is None:
                assignment = TaskAssignment(task=task, assignee=worker)
            assignment.assigned_by = source_membership.branch.owner
            assignment.shift = shift
            assignment.team = team
            assignment.status = (
                TaskAssignment.Status.PENDING
                if spec["status"] == HousekeepingTask.Status.PENDING_ACCEPTANCE
                else TaskAssignment.Status.ACCEPTED
            )
            assignment.is_current = True
            assignment.accepted_at = accepted_at
            assignment.ended_at = None
            assignment.note = "Phân công tự động cho bộ dữ liệu demo app."
            assignment.save()

            TaskSLAState.objects.update_or_create(
                task=task,
                defaults={
                    "policy": sla_policy,
                    "policy_snapshot": {
                        "acceptanceMinutes": 5,
                        "startMinutes": 10,
                        "completionMinutes": 45,
                        "checkinRiskBufferMinutes": 20,
                    },
                    "acceptance_due_at": task.acceptance_due_at,
                    "start_due_at": task.start_due_at,
                    "completion_due_at": task.due_at,
                    "acceptance_breached_at": (
                        now if spec["status"] == HousekeepingTask.Status.PENDING_ACCEPTANCE else None
                    ),
                    "start_breached_at": None,
                    "completion_breached_at": now if spec["overdue"] else None,
                    "checkin_risk_at": now if spec["checkin_risk"] else None,
                    "last_evaluated_at": now,
                },
            )
            self._task_checklist(
                task=task,
                worker=worker,
                definitions=definitions,
                completed_count=spec["completed_items"],
                now=now,
            )
            history = TaskStatusHistory.objects.filter(
                task=task,
                note="Dữ liệu demo app được đồng bộ tự động.",
            ).first()
            if history is None:
                TaskStatusHistory.objects.create(
                    task=task,
                    from_status="",
                    to_status=task.status,
                    changed_by=source_membership.branch.owner,
                    note="Dữ liệu demo app được đồng bộ tự động.",
                )
            elif history.to_status != task.status:
                history.to_status = task.status
                history.changed_by = source_membership.branch.owner
                history.save(update_fields=["to_status", "changed_by"])

        self._notifications(worker=worker, branch=branch, tasks=tasks, now=now)

        status_counts = {}
        for task in tasks.values():
            status_counts[task.status] = status_counts.get(task.status, 0) + 1
        status_text = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))
        self.stdout.write(
            self.style.SUCCESS(
                f"Đã sẵn sàng 8 công việc demo cho {worker.username} ngày {today:%d/%m/%Y} "
                f"(tạo mới {created_count}, cập nhật {8 - created_count}). {status_text}."
            )
        )

    def _checklist(self, *, branch, creator, now):
        template, _ = ChecklistTemplate.objects.update_or_create(
            branch=branch,
            code="APP-MOBILE-DEMO",
            defaults={
                "name": "Checklist demo app tạp vụ",
                "task_type": "",
                "is_active": True,
            },
        )
        version, _ = ChecklistVersion.objects.update_or_create(
            template=template,
            version_number=1,
            defaults={
                "version_label": "v1",
                "status": ChecklistVersion.Status.PUBLISHED,
                "policy_snapshot": {"source": "app-demo"},
                "published_at": now,
                "created_by": creator,
            },
        )
        definitions = []
        for order, (key, group, title) in enumerate(CHECKLIST_ITEMS, start=1):
            definition, _ = ChecklistItemDefinition.objects.update_or_create(
                version=version,
                key=key,
                defaults={
                    "group_name": group,
                    "title": title,
                    "item_type": TaskChecklistItem.ItemType.CHECKBOX,
                    "is_required": True,
                    "required_photo_count": 0,
                    "sort_order": order,
                },
            )
            definitions.append(definition)
        return version, definitions

    def _task_checklist(self, *, task, worker, definitions, completed_count, now):
        for order, definition in enumerate(definitions, start=1):
            is_completed = order <= completed_count
            TaskChecklistItem.objects.update_or_create(
                task=task,
                definition_key=definition.key,
                defaults={
                    "definition": definition,
                    "group_name": definition.group_name,
                    "title": definition.title,
                    "item_type": TaskChecklistItem.ItemType.CHECKBOX,
                    "is_required": True,
                    "requires_photo": False,
                    "status": (
                        TaskChecklistItem.Status.COMPLETED
                        if is_completed
                        else TaskChecklistItem.Status.PENDING
                    ),
                    "value": True if is_completed else None,
                    "completed_by": worker if is_completed else None,
                    "completed_at": now - timedelta(minutes=10) if is_completed else None,
                    "sort_order": order,
                },
            )

    def _notifications(self, *, worker, branch, tasks, now):
        specs = (
            (
                "APP_DEMO_CHECKIN_RISK",
                tasks["A202"],
                "A202 sắp check-in nhưng chưa sẵn sàng",
                "Khách dự kiến đến trong 60 phút. Ưu tiên hoàn tất và cập nhật trạng thái phòng.",
                "HIGH",
            ),
            (
                "APP_DEMO_OVERDUE",
                tasks["C103"],
                "C103 đã quá hạn hoàn thành",
                "Công việc đã quá SLA 10 phút và cần được xử lý ngay.",
                "HIGH",
            ),
            (
                "APP_DEMO_PAUSED",
                tasks["C201"],
                "C201 đang tạm dừng vì thiếu vật tư",
                "Cần bổ sung khăn tắm để nhân viên tiếp tục công việc.",
                "MEDIUM",
            ),
        )
        for notification_type, task, title, body, priority in specs:
            notification, _ = Notification.objects.get_or_create(
                branch=branch,
                task=task,
                notification_type=notification_type,
                object_type="APP_DEMO_TASK",
                object_id=str(task.id),
                defaults={"title": title, "body": body},
            )
            notification.title = title
            notification.body = body
            notification.payload = {
                "demo": True,
                "priority": priority,
                "taskId": str(task.id),
                "roomCode": task.room.code,
            }
            notification.save(update_fields=["title", "body", "payload"])
            NotificationRecipient.objects.update_or_create(
                notification=notification,
                user=worker,
                defaults={"delivered_at": now, "read_at": None},
            )

    def _task_specs(self, now):
        return (
            {
                "room": "A202",
                "floor": "Tầng 2",
                "task_type": HousekeepingTask.TaskType.CHECKIN_PREPARATION,
                "priority": HousekeepingTask.Priority.URGENT,
                "status": HousekeepingTask.Status.ASSIGNED,
                "progress": 0,
                "estimated_income": 90000,
                "completed_items": 0,
                # Hạn hoàn tất nằm sau giờ khách đến để API đánh dấu đúng
                # tình huống nguy cơ trễ check-in trên app.
                "due_at": now + timedelta(minutes=65),
                "next_checkin_at": now + timedelta(minutes=60),
                "checkin_at": now + timedelta(minutes=60),
                "checkout_at": now + timedelta(days=2),
                "booking_status": Booking.Status.BOOKED,
                "guest_name": "Khách sắp đến",
                "guest_count": 2,
                "special_request": "Chuẩn bị nôi em bé và thêm hai chai nước.",
                "special_request_items": ["Nôi em bé", "2 chai nước"],
                "note": "Ưu tiên cao vì khách sắp nhận phòng.",
                "pause_reason": "",
                "room_status": Room.Status.WAITING_CLEANING,
                "room_note": "Khách check-in sau 60 phút, phòng chưa sẵn sàng.",
                "overdue": False,
                "checkin_risk": True,
            },
            {
                "room": "B301",
                "floor": "Tầng 3",
                "task_type": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
                "priority": HousekeepingTask.Priority.HIGH,
                "status": HousekeepingTask.Status.IN_PROGRESS,
                "progress": 40,
                "estimated_income": 80000,
                "completed_items": 2,
                "due_at": now + timedelta(minutes=18),
                "next_checkin_at": now + timedelta(hours=2),
                "checkin_at": now - timedelta(days=2),
                "checkout_at": now - timedelta(minutes=35),
                "booking_status": Booking.Status.CHECKED_OUT,
                "guest_name": "Khách vừa trả phòng",
                "guest_count": 3,
                "special_request": "Khử mùi và kiểm tra minibar.",
                "special_request_items": ["Khử mùi", "Kiểm tra minibar"],
                "note": "Đang thực hiện, đã hoàn tất khu vực phòng ngủ.",
                "pause_reason": "",
                "room_status": Room.Status.CLEANING,
                "room_note": "Housekeeping đang dọn sau check-out.",
                "overdue": False,
                "checkin_risk": False,
            },
            {
                "room": "S201",
                "floor": "Tầng 2",
                "task_type": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.COMPLETED,
                "progress": 100,
                "estimated_income": 75000,
                "completed_items": 5,
                "due_at": now + timedelta(minutes=30),
                "next_checkin_at": None,
                "checkin_at": now - timedelta(days=3),
                "checkout_at": now - timedelta(hours=1),
                "booking_status": Booking.Status.CHECKED_OUT,
                "guest_name": "Khách đã trả phòng",
                "guest_count": 2,
                "special_request": "",
                "special_request_items": [],
                "note": "Đã hoàn thành đúng hạn.",
                "pause_reason": "",
                "room_status": Room.Status.READY,
                "room_note": "Đã dọn sạch và sẵn sàng bán.",
                "overdue": False,
                "checkin_risk": False,
            },
            {
                "room": "B102",
                "floor": "Tầng 1",
                "task_type": HousekeepingTask.TaskType.CHECKIN_PREPARATION,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.PENDING_ACCEPTANCE,
                "progress": 0,
                "estimated_income": 70000,
                "completed_items": 0,
                "due_at": now + timedelta(hours=2),
                "next_checkin_at": now + timedelta(hours=3),
                "checkin_at": now + timedelta(hours=3),
                "checkout_at": now + timedelta(days=2),
                "booking_status": Booking.Status.BOOKED,
                "guest_name": "Gia đình Nguyễn",
                "guest_count": 4,
                "special_request": "Xếp thêm một giường phụ.",
                "special_request_items": ["Giường phụ"],
                "note": "Công việc đang chờ nhân viên nhận.",
                "pause_reason": "",
                "room_status": Room.Status.WAITING_CLEANING,
                "room_note": "Chờ tạp vụ nhận việc.",
                "overdue": False,
                "checkin_risk": False,
            },
            {
                "room": "C103",
                "floor": "Tầng 1",
                "task_type": HousekeepingTask.TaskType.DEEP_CLEANING,
                "priority": HousekeepingTask.Priority.HIGH,
                "status": HousekeepingTask.Status.ACCEPTED,
                "progress": 0,
                "estimated_income": 110000,
                "completed_items": 0,
                "due_at": now - timedelta(minutes=10),
                "next_checkin_at": None,
                "checkin_at": now - timedelta(days=1),
                "checkout_at": now - timedelta(hours=2),
                "booking_status": Booking.Status.CHECKED_OUT,
                "guest_name": "Khách đã trả phòng",
                "guest_count": 2,
                "special_request": "Vệ sinh sâu khu vực bếp.",
                "special_request_items": ["Vệ sinh bếp"],
                "note": "Đã quá SLA, chưa bắt đầu thực hiện.",
                "pause_reason": "",
                "room_status": Room.Status.WAITING_CLEANING,
                "room_note": "Quá hạn dọn phòng 10 phút.",
                "overdue": True,
                "checkin_risk": False,
            },
            {
                "room": "C201",
                "floor": "Tầng 2",
                "task_type": HousekeepingTask.TaskType.STAYOVER_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.PAUSED,
                "progress": 20,
                "estimated_income": 60000,
                "completed_items": 1,
                "due_at": now + timedelta(minutes=35),
                "next_checkin_at": None,
                "checkin_at": now - timedelta(days=1),
                "checkout_at": now + timedelta(days=1),
                "booking_status": Booking.Status.CHECKED_IN,
                "guest_name": "Khách đang lưu trú",
                "guest_count": 2,
                "special_request": "Thay toàn bộ khăn tắm.",
                "special_request_items": ["Thay khăn tắm"],
                "note": "Đang chờ kho bổ sung khăn tắm.",
                "pause_reason": "SUPPLY_MISSING",
                "room_status": Room.Status.CLEANING_BLOCKED,
                "room_note": "Tạm dừng do thiếu vật tư.",
                "overdue": False,
                "checkin_risk": False,
            },
            {
                "room": "C202",
                "floor": "Tầng 2",
                "task_type": HousekeepingTask.TaskType.CHECKOUT_CLEANING,
                "priority": HousekeepingTask.Priority.NORMAL,
                "status": HousekeepingTask.Status.WAITING_QC,
                "progress": 100,
                "estimated_income": 85000,
                "completed_items": 5,
                "due_at": now + timedelta(minutes=40),
                "next_checkin_at": now + timedelta(hours=4),
                "checkin_at": now - timedelta(days=2),
                "checkout_at": now - timedelta(hours=1),
                "booking_status": Booking.Status.CHECKED_OUT,
                "guest_name": "Khách đã trả phòng",
                "guest_count": 1,
                "special_request": "",
                "special_request_items": [],
                "note": "Đã dọn xong, đang chờ QC kiểm tra.",
                "pause_reason": "",
                "room_status": Room.Status.WAITING_QC,
                "room_note": "Chờ kiểm tra chất lượng.",
                "overdue": False,
                "checkin_risk": False,
            },
            {
                "room": "C203",
                "floor": "Tầng 2",
                "task_type": HousekeepingTask.TaskType.PERIODIC_CLEANING,
                "priority": HousekeepingTask.Priority.LOW,
                "status": HousekeepingTask.Status.COMPLETED,
                "progress": 100,
                "estimated_income": 50000,
                "completed_items": 5,
                "due_at": now + timedelta(hours=1),
                "next_checkin_at": None,
                "checkin_at": None,
                "checkout_at": None,
                "booking_status": Booking.Status.BOOKED,
                "guest_name": "",
                "guest_count": 1,
                "special_request": "",
                "special_request_items": [],
                "note": "Vệ sinh định kỳ đã hoàn thành.",
                "pause_reason": "",
                "room_status": Room.Status.READY,
                "room_note": "Phòng trống sạch.",
                "overdue": False,
                "checkin_risk": False,
            },
        )
