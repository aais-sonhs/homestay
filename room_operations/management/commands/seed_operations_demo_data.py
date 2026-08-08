import base64
from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from housekeeping.models import (
    Booking,
    BookingChangeLog,
    BookingSpecialRequest,
    CapitalEntry,
    HousekeepingTask,
    IssueTicket,
    Notification,
    NotificationRecipient,
    OperatingExpense,
    OutboxEvent,
    QCTask,
    SupplyLocation,
    SupplyRequest,
    SupplyRequestItem,
    TaskAssignment,
    TaskChecklistItem,
    TaskPause,
    TaskPhoto,
    TaskSLAState,
    TaskStatusHistory,
)
from housekeeping.services import ensure_booking_housekeeping_tasks
from organizations.models import Area, Branch, Room
from reservations.special_requests import (
    replace_booking_special_requests,
    special_request_summary,
    task_special_request_items,
)
from room_operations.models import RoomAsset, RoomBlocker, RoomStopSell
from room_operations.services import (
    cancel_scheduled_stop_sell,
    confirm_room_reopen,
    create_room_stop_sell,
    ensure_issue_blocker,
    request_issue_blocker_clearance,
    request_room_reopen,
)


DEMO_CONTEXT = {
    "correlation_id": "demo-operations-seed",
    "device_id": "demo-seed-command",
}

ROOM_SPECS = (
    ("DALAT", "A103", "Phòng A103 — sẵn sàng", "Tầng 1", "Khu A", Room.Status.READY, False, False),
    ("DALAT", "A104", "Phòng A104 — đang có khách", "Tầng 1", "Khu A", Room.Status.READY, True, False),
    ("DALAT", "A202", "Phòng A202 — check-in có rủi ro", "Tầng 2", "Khu A", Room.Status.WAITING_CLEANING, False, False),
    ("DALAT", "B303", "Phòng B303 — sự cố dừng bán", "Tầng 3", "Khu B", Room.Status.CLEANING_BLOCKED, False, False),
    ("DALAT", "B304", "Phòng B304 — chờ gỡ blocker", "Tầng 3", "Khu B", Room.Status.READY, False, False),
    ("DALAT", "B305", "Phòng B305 — lịch dừng bán tương lai", "Tầng 3", "Khu B", Room.Status.READY, False, False),
    ("DALAT", "B306", "Phòng B306 — chờ xác nhận mở lại", "Tầng 3", "Khu B", Room.Status.READY, False, False),
    ("HCM", "S102", "Phòng S102 — đã mở bán lại", "Tầng 1", "Khu S", Room.Status.READY, False, False),
    ("HCM", "S201", "Phòng S201 — chờ vật tư", "Tầng 2", "Khu S", Room.Status.WAITING_CLEANING, False, False),
    ("HCM", "S202", "Phòng S202 — booking đã hủy", "Tầng 2", "Khu S", Room.Status.READY, False, False),
    ("HCM", "S203", "Phòng S203 — quản lý khóa", "Tầng 2", "Khu S", Room.Status.READY, False, True),
)

TODAY_REQUESTS = (
    {
        "request_type": BookingSpecialRequest.RequestType.BEDDING,
        "applies_to": BookingSpecialRequest.AppliesTo.CHECKIN,
        "priority": BookingSpecialRequest.Priority.HIGH,
        "description": "Ghép hai giường đơn thành một giường lớn.",
        "quantity": 1,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.AMENITY,
        "applies_to": BookingSpecialRequest.AppliesTo.ALL,
        "priority": BookingSpecialRequest.Priority.NORMAL,
        "description": "Bổ sung nước suối trong phòng.",
        "quantity": 4,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.ARRIVAL,
        "applies_to": BookingSpecialRequest.AppliesTo.CHECKIN,
        "priority": BookingSpecialRequest.Priority.NORMAL,
        "description": "Khách nhận phòng muộn, giữ đèn hiên và gửi hướng dẫn tự check-in.",
        "quantity": None,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.ACCESSIBILITY,
        "applies_to": BookingSpecialRequest.AppliesTo.ALL,
        "priority": BookingSpecialRequest.Priority.HIGH,
        "description": "Bố trí lối đi rộng, không đặt vật dụng sát cửa phòng tắm.",
        "quantity": None,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.HOUSEKEEPING,
        "applies_to": BookingSpecialRequest.AppliesTo.STAY,
        "priority": BookingSpecialRequest.Priority.NORMAL,
        "description": "Dọn phòng sau 14:00 và không dùng nước hoa phòng.",
        "quantity": None,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.CELEBRATION,
        "applies_to": BookingSpecialRequest.AppliesTo.CHECKIN,
        "priority": BookingSpecialRequest.Priority.HIGH,
        "description": "Trang trí sinh nhật tối giản và đặt thiệp chúc mừng.",
        "quantity": 1,
    },
    {
        "request_type": BookingSpecialRequest.RequestType.OTHER,
        "applies_to": BookingSpecialRequest.AppliesTo.CHECKOUT,
        "priority": BookingSpecialRequest.Priority.NORMAL,
        "description": "Kiểm tra và bàn giao lại một bộ sạc khách gửi lễ tân.",
        "quantity": 1,
    },
)


class Command(BaseCommand):
    help = (
        "Tạo bộ dữ liệu demo theo tình huống cho Booking, Housekeeping, readiness, "
        "blocker và stop-sell. Có thể chạy lại mà không nhân bản dữ liệu DEMO."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Đặt lại mật khẩu các tài khoản demo về mật khẩu mặc định.",
        )

    def handle(self, *args, **options):
        prerequisite_output = StringIO()
        call_command(
            "seed_demo_data",
            reset_passwords=options["reset_passwords"],
            stdout=prerequisite_output,
        )
        call_command("seed_housekeeping_data", stdout=prerequisite_output)

        try:
            with transaction.atomic():
                summary = self._seed_scenarios()
        except Exception as error:
            raise CommandError(f"Không thể tạo dữ liệu demo vận hành: {error}") from error

        self.stdout.write(
            self.style.SUCCESS(
                "Dữ liệu demo vận hành đã sẵn sàng: "
                f"{summary['rooms']} phòng tình huống, "
                f"{summary['bookings']} booking DEMO, "
                f"{summary['tasks']} task liên quan, "
                f"{summary['blockers']} blocker và "
                f"{summary['stop_sells']} stop-sell."
            )
        )
        self.stdout.write(
            "Mở Lịch vận hành ở ngày hôm nay; dùng menu Trạng thái phòng, "
            "Booking và Dừng bán phòng để xem toàn bộ tình huống."
        )

    def _seed_scenarios(self):
        now = timezone.now()
        local_now = timezone.localtime(now)
        today_at = lambda hour, minute=0: local_now.replace(
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
        users = {
            username: User.objects.get(username=username)
            for username in (
                "admin",
                "manager",
                "housekeeping",
                "housekeeping_lead",
                "qc",
                "technician",
                "warehouse",
                "sales",
            )
        }
        branches = {
            branch.code: branch
            for branch in Branch.objects.filter(code__in={"DALAT", "HCM"})
        }
        if set(branches) != {"DALAT", "HCM"}:
            raise CommandError("Thiếu chi nhánh DALAT hoặc HCM sau bước seed nền tảng.")

        rooms = self._seed_rooms(branches)
        booking_specs = (
            {
                "key": "TODAY",
                "code": "DEMO-BK-CHECKIN-TODAY",
                "room": rooms["A202"],
                "status": Booking.Status.BOOKED,
                "checkin_at": today_at(14),
                "checkout_at": today_at(11) + timedelta(days=2),
                "guest_name": "Nguyễn Minh Anh",
                "guest_phone": "0909000101",
                "guest_count": 3,
                "room_charge": Decimal("2400000.00"),
                "service_charge": Decimal("300000.00"),
                "discount_amount": Decimal("200000.00"),
                "paid_amount": Decimal("1000000.00"),
                "requests": TODAY_REQUESTS,
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.IN_PROGRESS,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.UNASSIGNED,
                },
            },
            {
                "key": "OCCUPIED",
                "code": "DEMO-BK-OCCUPIED",
                "room": rooms["A104"],
                "status": Booking.Status.CHECKED_IN,
                "checkin_at": today_at(10),
                "checkout_at": today_at(17),
                "guest_name": "Trần Gia Đình",
                "guest_phone": "0909000102",
                "guest_count": 4,
                "room_charge": Decimal("1800000.00"),
                "service_charge": Decimal("160000.00"),
                "discount_amount": Decimal("0.00"),
                "paid_amount": Decimal("1960000.00"),
                "requests": (
                    {
                        "request_type": BookingSpecialRequest.RequestType.HOUSEKEEPING,
                        "applies_to": BookingSpecialRequest.AppliesTo.STAY,
                        "priority": BookingSpecialRequest.Priority.NORMAL,
                        "description": "Thay khăn mỗi ngày lúc 15:00, khách vẫn ở trong phòng.",
                        "quantity": 4,
                    },
                ),
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.QC_APPROVED,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.UNASSIGNED,
                },
            },
            {
                "key": "FUTURE",
                "code": "DEMO-BK-FUTURE",
                "room": rooms["A103"],
                "status": Booking.Status.BOOKED,
                "checkin_at": now + timedelta(days=3),
                "checkout_at": now + timedelta(days=5),
                "guest_name": "Lê Hoàng Nam",
                "guest_phone": "0909000103",
                "guest_count": 2,
                "room_charge": Decimal("0.00"),
                "service_charge": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "paid_amount": Decimal("0.00"),
                "requests": (),
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.UNASSIGNED,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.UNASSIGNED,
                },
            },
            {
                "key": "AFFECTED",
                "code": "DEMO-BK-AFFECTED-BY-STOP-SELL",
                "room": rooms["B303"],
                "status": Booking.Status.BOOKED,
                "checkin_at": today_at(16),
                "checkout_at": today_at(12) + timedelta(days=2),
                "guest_name": "Phạm Thảo Vy",
                "guest_phone": "0909000104",
                "guest_count": 2,
                "room_charge": Decimal("1600000.00"),
                "service_charge": Decimal("250000.00"),
                "discount_amount": Decimal("0.00"),
                "paid_amount": Decimal("500000.00"),
                "requests": (
                    {
                        "request_type": BookingSpecialRequest.RequestType.AMENITY,
                        "applies_to": BookingSpecialRequest.AppliesTo.CHECKIN,
                        "priority": BookingSpecialRequest.Priority.HIGH,
                        "description": "Chuẩn bị máy lọc không khí trước khi khách đến.",
                        "quantity": 1,
                    },
                ),
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.UNASSIGNED,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.UNASSIGNED,
                },
            },
            {
                "key": "CHECKED_OUT",
                "code": "DEMO-BK-CHECKED-OUT",
                "room": rooms["S201"],
                "status": Booking.Status.CHECKED_OUT,
                "checkin_at": today_at(15) - timedelta(days=2),
                "checkout_at": today_at(11),
                "guest_name": "Võ Quang Huy",
                "guest_phone": "0909000105",
                "guest_count": 2,
                "room_charge": Decimal("1400000.00"),
                "service_charge": Decimal("180000.00"),
                "discount_amount": Decimal("80000.00"),
                "paid_amount": Decimal("1500000.00"),
                "requests": (
                    {
                        "request_type": BookingSpecialRequest.RequestType.OTHER,
                        "applies_to": BookingSpecialRequest.AppliesTo.CHECKOUT,
                        "priority": BookingSpecialRequest.Priority.NORMAL,
                        "description": "Kiểm tra minibar và báo đồ thất lạc sau checkout.",
                        "quantity": None,
                    },
                ),
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.QC_APPROVED,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.WAITING_SUPPORT,
                },
            },
            {
                "key": "CANCELLED",
                "code": "DEMO-BK-CANCELLED",
                "room": rooms["S202"],
                "status": Booking.Status.CANCELLED,
                "checkin_at": now + timedelta(days=1),
                "checkout_at": now + timedelta(days=2),
                "guest_name": "Đỗ Thu Hà",
                "guest_phone": "0909000106",
                "guest_count": 1,
                "room_charge": Decimal("900000.00"),
                "service_charge": Decimal("0.00"),
                "discount_amount": Decimal("0.00"),
                "paid_amount": Decimal("0.00"),
                "requests": (),
                "task_statuses": {
                    HousekeepingTask.TaskType.CHECKIN_PREPARATION: HousekeepingTask.Status.CANCELLED,
                    HousekeepingTask.TaskType.CHECKOUT_CLEANING: HousekeepingTask.Status.CANCELLED,
                },
            },
        )

        bookings = {}
        tasks = {}
        for spec in booking_specs:
            booking, booking_tasks = self._seed_booking(spec, users, now)
            bookings[spec["key"]] = booking
            tasks[spec["key"]] = {
                task.task_type: task for task in booking_tasks
            }

        tasks["PAUSED"] = self._seed_standalone_task(
            rooms["A104"],
            "DEMO-HK-A104-STAYOVER-PAUSED",
            HousekeepingTask.TaskType.STAYOVER_CLEANING,
            HousekeepingTask.Status.PAUSED,
            users["housekeeping"],
            users,
            now,
            "Khách đề nghị quay lại sau 16:00.",
        )
        tasks["CLEARANCE"] = self._seed_standalone_task(
            rooms["B304"],
            "DEMO-HK-B304-POST-REPAIR-CHECK",
            HousekeepingTask.TaskType.DEEP_CLEANING,
            HousekeepingTask.Status.COMPLETED,
            users["housekeeping"],
            users,
            now,
            "Đã vệ sinh sau sửa khóa; chờ quản lý xác nhận phòng.",
        )
        tasks["REWORK"] = self._seed_standalone_task(
            rooms["A202"],
            "DEMO-HK-A202-QC-REWORK",
            HousekeepingTask.TaskType.QC_REWORK,
            HousekeepingTask.Status.QC_REJECTED,
            users["housekeeping"],
            users,
            now,
            "QC không đạt do khu vực phòng tắm còn vệt nước; cần làm lại.",
        )
        tasks["OVERDUE"] = self._seed_standalone_task(
            rooms["B305"],
            "DEMO-HK-B305-OVERDUE",
            HousekeepingTask.TaskType.PERIODIC_CLEANING,
            HousekeepingTask.Status.IN_PROGRESS,
            users["housekeeping_lead"],
            users,
            now,
            "Công việc vệ sinh định kỳ đã quá SLA và cần điều phối hỗ trợ.",
            due_at=now - timedelta(minutes=45),
        )

        self._seed_supply_case(tasks["CHECKED_OUT"][HousekeepingTask.TaskType.CHECKOUT_CLEANING], users)
        issues = self._seed_issue_and_blocker_cases(rooms, tasks, bookings, users, now)
        stop_sells = self._seed_stop_sell_cases(rooms, issues, users, now)
        self._seed_photos_and_notifications(tasks, issues, users)
        self._seed_asset_cases(rooms, now)
        self._seed_cost_cases(branches, users, now)
        self._seed_financial_comparison_case(branches, rooms, users, now)

        demo_bookings = Booking.objects.filter(code__startswith="DEMO-BK-")
        booking_tasks = HousekeepingTask.objects.filter(booking__in=demo_bookings).count()
        standalone_tasks = HousekeepingTask.objects.filter(code__startswith="DEMO-HK-").count()
        demo_blockers = RoomBlocker.objects.filter(reason__contains="[DEMO:")
        demo_stop_sells = RoomStopSell.objects.filter(reason__startswith="[DEMO:")
        return {
            "rooms": len(rooms),
            "bookings": demo_bookings.count(),
            "tasks": booking_tasks + standalone_tasks,
            "blockers": demo_blockers.count(),
            "stop_sells": demo_stop_sells.count(),
        }

    def _seed_cost_cases(self, branches, users, now):
        today = timezone.localdate(now)
        previous_month_last_day = today.replace(day=1) - timedelta(days=1)
        previous_date = previous_month_last_day.replace(
            day=min(today.day, previous_month_last_day.day)
        )
        cases = (
            (branches["DALAT"], "DEMO Vốn đầu tư phòng mẫu", Decimal("50000000.00"), "Chủ chi nhánh", "Vốn đầu tư ban đầu"),
            (branches["HCM"], "DEMO Vốn mở rộng khu S", Decimal("80000000.00"), "Nhà đầu tư", "Vốn bổ sung"),
        )
        for branch, title, amount, source, notes in cases:
            CapitalEntry.objects.get_or_create(
                branch=branch,
                title=title,
                capital_date=today,
                defaults={
                    "amount": amount,
                    "source": source,
                    "notes": notes,
                    "created_by": users["admin"],
                    "updated_by": users["manager"],
                },
            )
        expenses = (
            (branches["DALAT"], "DEMO Tiền điện tháng này", OperatingExpense.CategoryCode.UTILITIES, "Điện nước", Decimal("3200000.00"), OperatingExpense.PaymentStatus.PAID),
            (branches["DALAT"], "DEMO Mua khăn bổ sung", OperatingExpense.CategoryCode.HOUSEKEEPING, "Vật tư buồng phòng", Decimal("1500000.00"), OperatingExpense.PaymentStatus.PLANNED),
            (branches["DALAT"], "DEMO Chi phí dọn phòng tháng này", OperatingExpense.CategoryCode.HOUSEKEEPING, "Housekeeping", Decimal("1100000.00"), OperatingExpense.PaymentStatus.PAID),
            (branches["HCM"], "DEMO Sửa khóa phòng S203", OperatingExpense.CategoryCode.TECHNICAL_MAINTENANCE, "Sửa chữa", Decimal("2800000.00"), OperatingExpense.PaymentStatus.PAID),
            (branches["DALAT"], "DEMO Điện nước tháng trước", OperatingExpense.CategoryCode.UTILITIES, "Điện nước", Decimal("2500000.00"), OperatingExpense.PaymentStatus.PAID, previous_date),
            (branches["DALAT"], "DEMO Housekeeping tháng trước", OperatingExpense.CategoryCode.HOUSEKEEPING, "Housekeeping", Decimal("900000.00"), OperatingExpense.PaymentStatus.PAID, previous_date),
            (branches["HCM"], "DEMO Bảo trì tháng trước", OperatingExpense.CategoryCode.TECHNICAL_MAINTENANCE, "Bảo trì", Decimal("1600000.00"), OperatingExpense.PaymentStatus.PAID, previous_date),
        )
        for expense in expenses:
            branch, name, category_code, category, amount, payment_status, *expense_dates = expense
            expense_date = expense_dates[0] if expense_dates else today
            OperatingExpense.objects.update_or_create(
                branch=branch,
                name=name,
                defaults={
                    "expense_date": expense_date,
                    "category_code": category_code,
                    "category": category,
                    "amount": amount,
                    "payment_status": payment_status,
                    "notes": "Dữ liệu mẫu do seed_operations_demo_data quản lý.",
                    "created_by": users["admin"],
                    "updated_by": users["manager"],
                },
            )

    def _seed_financial_comparison_case(self, branches, rooms, users, now):
        today = timezone.localdate(now)
        previous_month_last_day = today.replace(day=1) - timedelta(days=1)
        previous_date = previous_month_last_day.replace(
            day=min(today.day, previous_month_last_day.day)
        )
        previous_checkout_at = now - timedelta(days=(today - previous_date).days)
        Booking.objects.update_or_create(
            branch=branches["DALAT"],
            code="DEMO-FIN-PREVIOUS-MONTH",
            defaults={
                "room": rooms["A103"],
                "status": Booking.Status.CHECKED_OUT,
                "checkin_at": previous_checkout_at - timedelta(days=2),
                "checkout_at": previous_checkout_at,
                "guest_name": "Khách so sánh tháng trước",
                "guest_phone": "0909000199",
                "guest_count": 2,
                "special_requests": "Dữ liệu mẫu dùng để tính phần trăm so sánh tháng.",
                "room_charge": Decimal("1000000.00"),
                "service_charge": Decimal("100000.00"),
                "discount_amount": Decimal("100000.00"),
                "paid_amount": Decimal("1000000.00"),
                "source": Booking.Source.MANUAL_SALES,
                "created_by": users["sales"],
                "updated_by": users["manager"],
            },
        )

    def _seed_asset_cases(self, rooms, now):
        today = timezone.localdate(now)
        specs = (
            (rooms["A103"], "DEMO-AC-A103", "Điều hòa A103", RoomAsset.Category.AIR_CONDITIONER, RoomAsset.Status.OPERATIONAL, today + timedelta(days=45)),
            (rooms["A104"], "DEMO-TV-A104", "Tivi A104", RoomAsset.Category.TELEVISION, RoomAsset.Status.OPERATIONAL, today + timedelta(days=90)),
            (rooms["A202"], "DEMO-WH-A202", "Bình nóng lạnh A202", RoomAsset.Category.WATER_HEATER, RoomAsset.Status.MAINTENANCE, today - timedelta(days=2)),
            (rooms["B303"], "DEMO-AC-B303", "Điều hòa B303", RoomAsset.Category.AIR_CONDITIONER, RoomAsset.Status.FAULT, today),
            (rooms["S203"], "DEMO-LOCK-S203", "Khóa cửa thông minh S203", RoomAsset.Category.DOOR_LOCK, RoomAsset.Status.MAINTENANCE, today + timedelta(days=7)),
        )
        for room, code, name, category, status, next_maintenance_at in specs:
            RoomAsset.objects.update_or_create(
                branch=room.branch,
                code=code,
                defaults={
                    "room": room,
                    "name": name,
                    "category": category,
                    "status": status,
                    "next_maintenance_at": next_maintenance_at,
                    "note": "Dữ liệu mẫu do seed_operations_demo_data quản lý.",
                    "is_active": True,
                },
            )

    def _seed_rooms(self, branches):
        rooms = {}
        for branch_code, code, name, floor, area_name, status, occupied, locked in ROOM_SPECS:
            branch = branches[branch_code]
            area, _ = Area.objects.get_or_create(
                branch=branch,
                code=f"DEMO-{area_name.replace(' ', '-').upper()}",
                defaults={"name": area_name, "floor_label": floor},
            )
            room, _ = Room.objects.update_or_create(
                branch=branch,
                code=code,
                defaults={
                    "name": name,
                    "floor": floor,
                    "area": area_name,
                    "area_ref": area,
                    "room_type": "Demo tình huống",
                    "status": status,
                    "is_guest_occupied": occupied,
                    "is_locked": locked,
                    "operational_note": (
                        "Dữ liệu mẫu do seed_operations_demo_data quản lý."
                    ),
                },
            )
            rooms[code] = room
        return rooms

    def _seed_booking(self, spec, users, now):
        booking, _ = Booking.objects.get_or_create(
            branch=spec["room"].branch,
            code=spec["code"],
            defaults={"room": spec["room"]},
        )
        # Temporarily keep the booking non-terminal so the idempotent automation
        # can guarantee both standard tasks exist on every run.
        booking.room = spec["room"]
        booking.status = Booking.Status.BOOKED
        booking.checkin_at = spec["checkin_at"]
        booking.checkout_at = spec["checkout_at"]
        booking.guest_name = spec["guest_name"]
        booking.guest_phone = spec["guest_phone"]
        booking.guest_count = spec["guest_count"]
        booking.room_charge = spec["room_charge"]
        booking.service_charge = spec["service_charge"]
        booking.discount_amount = spec["discount_amount"]
        booking.paid_amount = spec["paid_amount"]
        booking.source = Booking.Source.MANUAL_SALES
        booking.created_by = users["sales"]
        booking.updated_by = users["manager"]
        booking.version = 2 if spec["status"] == Booking.Status.CANCELLED else 1
        booking.cancelled_by = None
        booking.cancelled_at = None
        booking.cancellation_reason = ""
        booking.save()

        request_rows = [dict(item) for item in spec["requests"]]
        replace_booking_special_requests(booking, request_rows, users["sales"])
        booking.special_requests = special_request_summary(request_rows)
        booking.save(update_fields=["special_requests", "updated_at"])
        booking_tasks = ensure_booking_housekeeping_tasks(
            users["admin"], booking, DEMO_CONTEXT
        )
        if not booking_tasks:
            booking_tasks = list(booking.housekeeping_tasks.order_by("task_type", "id"))

        assignee = (
            users["housekeeping"]
            if booking.branch.code == "DALAT"
            else users["housekeeping_lead"]
        )
        for task in booking_tasks:
            self._set_task_scenario_state(
                task,
                spec["task_statuses"][task.task_type],
                assignee,
                users,
                now,
            )

        booking.status = spec["status"]
        if spec["status"] == Booking.Status.CANCELLED:
            booking.cancelled_by = users["sales"]
            booking.cancelled_at = now - timedelta(minutes=20)
            booking.cancellation_reason = "[DEMO] Khách đổi kế hoạch và hủy trong thời hạn cho phép."
        booking.save(
            update_fields=[
                "status",
                "cancelled_by",
                "cancelled_at",
                "cancellation_reason",
                "updated_at",
            ]
        )
        self._ensure_booking_audit(booking, users)
        return booking, booking_tasks

    def _set_task_scenario_state(self, task, status, assignee, users, now):
        checkin_task = task.task_type == HousekeepingTask.TaskType.CHECKIN_PREPARATION
        if checkin_task:
            scheduled_start = task.booking.checkin_at - timedelta(minutes=90)
            due_at = task.booking.checkin_at - timedelta(minutes=30)
        else:
            scheduled_start = task.booking.checkout_at
            due_at = task.booking.checkout_at + timedelta(minutes=60)
        task.scheduled_start_at = scheduled_start
        task.acceptance_due_at = scheduled_start - timedelta(minutes=30)
        task.start_due_at = scheduled_start + timedelta(minutes=15)
        task.due_at = due_at
        task.standard_duration_minutes = max(
            1, int((due_at - scheduled_start).total_seconds() // 60)
        )
        task.status = status
        task.special_request_items = task_special_request_items(task.booking, task.task_type)
        task.special_request = special_request_summary(task.special_request_items)
        task.updated_by = users["manager"]
        task.assignee = None
        task.assigned_by = None
        task.accepted_at = None
        task.started_at = None
        task.completed_at = None
        task.cancelled_at = None
        task.cancelled_by = None
        task.cancellation_reason = ""
        task.pause_reason = ""
        task.progress_percent = 0

        assigned_statuses = {
            HousekeepingTask.Status.ACCEPTED,
            HousekeepingTask.Status.IN_PROGRESS,
            HousekeepingTask.Status.PAUSED,
            HousekeepingTask.Status.WAITING_SUPPORT,
            HousekeepingTask.Status.COMPLETED,
            HousekeepingTask.Status.WAITING_QC,
            HousekeepingTask.Status.QC_REJECTED,
            HousekeepingTask.Status.QC_APPROVED,
        }
        if status in assigned_statuses:
            task.assignee = assignee
            task.assigned_by = users["manager"]
            task.accepted_at = min(now - timedelta(hours=2), scheduled_start)
        if status in {
            HousekeepingTask.Status.IN_PROGRESS,
            HousekeepingTask.Status.PAUSED,
            HousekeepingTask.Status.WAITING_SUPPORT,
            HousekeepingTask.Status.COMPLETED,
            HousekeepingTask.Status.WAITING_QC,
            HousekeepingTask.Status.QC_REJECTED,
            HousekeepingTask.Status.QC_APPROVED,
        }:
            task.started_at = min(now - timedelta(minutes=50), scheduled_start)
            task.progress_percent = 40
        if status == HousekeepingTask.Status.WAITING_SUPPORT:
            task.pause_reason = "WAITING_SUPPLIES"
            task.progress_percent = 65
        if status in {
            HousekeepingTask.Status.COMPLETED,
            HousekeepingTask.Status.WAITING_QC,
            HousekeepingTask.Status.QC_REJECTED,
            HousekeepingTask.Status.QC_APPROVED,
        }:
            task.completed_at = now - timedelta(minutes=30)
            task.progress_percent = 100
        if status == HousekeepingTask.Status.CANCELLED:
            task.cancelled_at = now - timedelta(minutes=20)
            task.cancelled_by = users["sales"]
            task.cancellation_reason = "[DEMO] Booking đã hủy."
        task.save()

        sla_state, _ = TaskSLAState.objects.get_or_create(task=task)
        sla_state.acceptance_due_at = task.acceptance_due_at
        sla_state.start_due_at = task.start_due_at
        sla_state.completion_due_at = task.due_at
        sla_state.policy_snapshot = {
            **(sla_state.policy_snapshot or {}),
            "source": "DEMO_SCENARIO",
            "standardDurationMinutes": task.standard_duration_minutes,
        }
        sla_state.save(
            update_fields=[
                "acceptance_due_at",
                "start_due_at",
                "completion_due_at",
                "policy_snapshot",
                "updated_at",
            ]
        )

        TaskStatusHistory.objects.get_or_create(
            task=task,
            to_status=status,
            reason_code="DEMO_SCENARIO",
            defaults={
                "from_status": HousekeepingTask.Status.UNASSIGNED,
                "task_version": task.version,
                "changed_by": users["manager"],
                "note": "Trạng thái mẫu phục vụ kiểm thử giao diện.",
            },
        )
        if task.assignee_id:
            TaskAssignment.objects.get_or_create(
                task=task,
                assignee=task.assignee,
                reason_code="DEMO_SCENARIO",
                defaults={
                    "assigned_by": users["manager"],
                    "status": TaskAssignment.Status.ACCEPTED,
                    "is_current": status not in {
                        HousekeepingTask.Status.QC_APPROVED,
                        HousekeepingTask.Status.CANCELLED,
                    },
                    "accepted_at": task.accepted_at,
                    "note": "Phân công mẫu theo tình huống.",
                },
            )

        checklist_items = list(task.checklist_items.order_by("sort_order", "id"))
        for index, item in enumerate(checklist_items):
            completed = status == HousekeepingTask.Status.QC_APPROVED or (
                status in {
                    HousekeepingTask.Status.IN_PROGRESS,
                    HousekeepingTask.Status.WAITING_SUPPORT,
                }
                and index < 2
            )
            item.status = (
                TaskChecklistItem.Status.COMPLETED
                if completed
                else TaskChecklistItem.Status.PENDING
            )
            item.value = True if completed else None
            item.completed_by = assignee if completed else None
            item.completed_at = now - timedelta(minutes=35) if completed else None
            item.save(
                update_fields=["status", "value", "completed_by", "completed_at"]
            )

        if status == HousekeepingTask.Status.QC_APPROVED:
            QCTask.objects.update_or_create(
                task=task,
                round_number=1,
                defaults={
                    "status": QCTask.Status.APPROVED,
                    "reviewer": users["qc"],
                    "note": "[DEMO] Phòng đạt toàn bộ tiêu chí QC.",
                    "reviewed_at": now - timedelta(minutes=20),
                    "result_snapshot": {"result": "APPROVED", "source": "DEMO"},
                },
            )

    def _seed_standalone_task(
        self,
        room,
        code,
        task_type,
        status,
        assignee,
        users,
        now,
        note,
        *,
        due_at=None,
    ):
        due_at = due_at or now + timedelta(hours=1)
        is_qc_result = status in {
            HousekeepingTask.Status.QC_REJECTED,
            HousekeepingTask.Status.QC_APPROVED,
        }
        task, _ = HousekeepingTask.objects.update_or_create(
            code=code,
            defaults={
                "branch": room.branch,
                "room": room,
                "task_type": task_type,
                "priority": HousekeepingTask.Priority.HIGH,
                "status": status,
                "assignee": assignee,
                "assigned_by": users["manager"],
                "area": room.area_ref,
                "scheduled_start_at": now - timedelta(hours=2),
                "acceptance_due_at": now - timedelta(hours=2, minutes=30),
                "start_due_at": now - timedelta(hours=1, minutes=45),
                "due_at": due_at,
                "standard_duration_minutes": 180,
                "accepted_at": now - timedelta(hours=2),
                "started_at": now - timedelta(hours=1, minutes=45),
                "completed_at": (
                    now - timedelta(minutes=20)
                    if status == HousekeepingTask.Status.COMPLETED or is_qc_result
                    else None
                ),
                "progress_percent": (
                    100
                    if status == HousekeepingTask.Status.COMPLETED or is_qc_result
                    else 55
                ),
                "pause_reason": (
                    "GUEST_REQUEST_LATER"
                    if status == HousekeepingTask.Status.PAUSED
                    else ""
                ),
                "note": f"[DEMO] {note}",
                "rework_count": 1 if status == HousekeepingTask.Status.QC_REJECTED else 0,
                "current_rework_round": 1 if status == HousekeepingTask.Status.QC_REJECTED else 0,
                "rework_started_at": (
                    now - timedelta(minutes=15)
                    if status == HousekeepingTask.Status.QC_REJECTED
                    else None
                ),
                "created_by": users["manager"],
                "updated_by": users["manager"],
            },
        )
        TaskSLAState.objects.update_or_create(
            task=task,
            defaults={
                "acceptance_due_at": task.acceptance_due_at,
                "start_due_at": task.start_due_at,
                "completion_due_at": task.due_at,
                "policy_snapshot": {
                    "source": "DEMO_SCENARIO",
                    "standardDurationMinutes": task.standard_duration_minutes,
                },
            },
        )
        TaskStatusHistory.objects.get_or_create(
            task=task,
            to_status=status,
            reason_code="DEMO_SCENARIO",
            defaults={
                "from_status": HousekeepingTask.Status.IN_PROGRESS,
                "task_version": task.version,
                "changed_by": users["manager"],
                "note": note,
            },
        )
        TaskAssignment.objects.get_or_create(
            task=task,
            assignee=assignee,
            reason_code="DEMO_SCENARIO",
            defaults={
                "assigned_by": users["manager"],
                "status": TaskAssignment.Status.ACCEPTED,
                "accepted_at": task.accepted_at,
                "note": "Phân công mẫu theo tình huống.",
            },
        )
        if status == HousekeepingTask.Status.PAUSED:
            TaskPause.objects.get_or_create(
                task=task,
                reason_code="GUEST_REQUEST_LATER",
                resumed_at=None,
                defaults={
                    "previous_status": HousekeepingTask.Status.IN_PROGRESS,
                    "note": note,
                    "excluded_from_sla": True,
                    "paused_by": assignee,
                    "approved_by": users["manager"],
                    "approved_at": now - timedelta(minutes=25),
                },
            )
        if status == HousekeepingTask.Status.QC_REJECTED:
            QCTask.objects.update_or_create(
                task=task,
                round_number=1,
                defaults={
                    "status": QCTask.Status.REJECTED,
                    "reviewer": users["qc"],
                    "reason": "BATHROOM_WATER_MARKS",
                    "note": "[DEMO] Phòng tắm còn vệt nước, yêu cầu dọn lại.",
                    "reviewed_at": now - timedelta(minutes=20),
                    "result_snapshot": {"result": "REJECTED", "source": "DEMO"},
                },
            )
        return task

    def _ensure_booking_audit(self, booking, users):
        snapshot = {
            "bookingId": str(booking.id),
            "bookingCode": booking.code,
            "branchId": str(booking.branch_id),
            "roomId": str(booking.room_id),
            "status": booking.status,
            "checkinAt": booking.checkin_at.isoformat(),
            "checkoutAt": booking.checkout_at.isoformat(),
            "guestName": booking.guest_name,
            "guestPhone": booking.guest_phone,
            "guestCount": booking.guest_count,
            "roomCharge": str(booking.room_charge),
            "serviceCharge": str(booking.service_charge),
            "discountAmount": str(booking.discount_amount),
            "paidAmount": str(booking.paid_amount),
            "totalAmount": str(booking.total_amount),
            "outstandingAmount": str(booking.outstanding_amount),
            "specialRequests": booking.special_requests,
            "version": booking.version,
        }
        BookingChangeLog.objects.get_or_create(
            booking=booking,
            action=BookingChangeLog.Action.CREATED,
            booking_version=1,
            defaults={
                "branch": booking.branch,
                "changed_by": users["sales"],
                "after_snapshot": snapshot,
                "correlation_id": DEMO_CONTEXT["correlation_id"],
            },
        )
        if booking.status == Booking.Status.CANCELLED:
            BookingChangeLog.objects.get_or_create(
                booking=booking,
                action=BookingChangeLog.Action.CANCELLED,
                booking_version=booking.version,
                defaults={
                    "branch": booking.branch,
                    "changed_by": users["sales"],
                    "reason": booking.cancellation_reason,
                    "after_snapshot": snapshot,
                    "correlation_id": DEMO_CONTEXT["correlation_id"],
                },
            )
        OutboxEvent.objects.get_or_create(
            deduplication_key=f"demo:booking:{booking.code}:seeded"[:120],
            defaults={
                "event_type": "BOOKING_CREATED",
                "aggregate_type": "BOOKING",
                "aggregate_id": str(booking.id),
                "payload": {**snapshot, "source": "DEMO_SCENARIO"},
            },
        )

    def _seed_supply_case(self, task, users):
        destination = SupplyLocation.objects.get(
            branch=task.branch,
            code="DEFAULT",
        )
        supply_request, _ = SupplyRequest.objects.get_or_create(
            task=task,
            requested_by=task.assignee,
            client_request_id="DEMO-SUPPLY-S201",
            defaults={
                "branch": task.branch,
                "destination": destination,
                "priority": HousekeepingTask.Priority.URGENT,
                "note": "[DEMO] Thiếu ga giường cỡ king, đang chờ kho cấp.",
                "warehouse": destination.name,
                "blocks_completion": True,
                "status": SupplyRequest.Status.PENDING,
            },
        )
        SupplyRequestItem.objects.get_or_create(
            request=supply_request,
            inventory_item_id="DEMO-LINEN-KING",
            defaults={
                "item_name": "Bộ ga giường king",
                "quantity": 2,
                "unit": "bộ",
            },
        )
        return supply_request

    def _seed_issue_and_blocker_cases(self, rooms, tasks, bookings, users, now):
        active_task = tasks["AFFECTED"][HousekeepingTask.TaskType.CHECKIN_PREPARATION]
        active_issue, _ = IssueTicket.objects.get_or_create(
            task=active_task,
            reported_by=users["housekeeping"],
            client_request_id="DEMO-ISSUE-AIRCON-B303",
            defaults={
                "room": rooms["B303"],
                "booking": bookings["AFFECTED"],
                "assigned_to": users["technician"],
                "device_id": "AIRCON-B303",
                "issue_type": "AIR_CONDITIONER",
                "severity": HousekeepingTask.Priority.URGENT,
                "description": "[DEMO:ACTIVE-ISSUE] Điều hòa rò nước và không làm lạnh.",
                "blocks_room_ready": True,
                "status": IssueTicket.Status.IN_PROGRESS,
                "assigned_at": now - timedelta(minutes=35),
            },
        )
        active_blocker, _ = ensure_issue_blocker(
            active_issue, users["housekeeping"], DEMO_CONTEXT
        )

        clearance_task = tasks["CLEARANCE"]
        clearance_issue, _ = IssueTicket.objects.get_or_create(
            task=clearance_task,
            reported_by=users["housekeeping"],
            client_request_id="DEMO-ISSUE-LOCK-B304",
            defaults={
                "room": rooms["B304"],
                "assigned_to": users["technician"],
                "device_id": "DOOR-LOCK-B304",
                "issue_type": "DOOR_LOCK",
                "severity": HousekeepingTask.Priority.HIGH,
                "description": "[DEMO:CLEARANCE-PENDING] Khóa cửa điện tử chập chờn.",
                "blocks_room_ready": True,
                "status": IssueTicket.Status.RESOLVED,
                "resolved_by": users["technician"],
                "resolved_at": now - timedelta(minutes=25),
                "resolution_note": "Đã thay pin và kiểm tra mở khóa mười lần.",
            },
        )
        clearance_blocker, _ = ensure_issue_blocker(
            clearance_issue, users["housekeeping"], DEMO_CONTEXT
        )
        request_issue_blocker_clearance(
            clearance_issue,
            users["technician"],
            "Kỹ thuật đã sửa xong, đề nghị vận hành kiểm tra và gỡ blocker.",
            DEMO_CONTEXT,
        )
        return {
            "active": active_issue,
            "active_blocker": active_blocker,
            "clearance": clearance_issue,
            "clearance_blocker": clearance_blocker,
        }

    def _seed_stop_sell_cases(self, rooms, issues, users, now):
        scenarios = (
            {
                "marker": "ACTIVE-ISSUE-STOP-SELL",
                "room": rooms["B303"],
                "blocker": issues["active_blocker"],
                "reason_code": RoomStopSell.ReasonCode.MAINTENANCE,
                "starts_at": now - timedelta(minutes=2),
                "planned_end_at": now + timedelta(hours=30),
                "target": RoomStopSell.Status.ACTIVE,
            },
            {
                "marker": "SCHEDULED-STOP-SELL",
                "room": rooms["B305"],
                "blocker": None,
                "reason_code": RoomStopSell.ReasonCode.OWNER_HOLD,
                "starts_at": now + timedelta(days=2),
                "planned_end_at": now + timedelta(days=3),
                "target": RoomStopSell.Status.ACTIVE,
            },
            {
                "marker": "REOPEN-REQUESTED",
                "room": rooms["B306"],
                "blocker": None,
                "reason_code": RoomStopSell.ReasonCode.CLEANLINESS,
                "starts_at": now - timedelta(minutes=2),
                "planned_end_at": now + timedelta(hours=8),
                "target": RoomStopSell.Status.REOPEN_REQUESTED,
            },
            {
                "marker": "REOPENED",
                "room": rooms["S102"],
                "blocker": None,
                "reason_code": RoomStopSell.ReasonCode.MAINTENANCE,
                "starts_at": now - timedelta(minutes=2),
                "planned_end_at": now + timedelta(hours=6),
                "target": RoomStopSell.Status.ENDED,
            },
            {
                "marker": "CANCELLED-SCHEDULE",
                "room": rooms["S203"],
                "blocker": None,
                "reason_code": RoomStopSell.ReasonCode.OTHER,
                "starts_at": now + timedelta(days=4),
                "planned_end_at": now + timedelta(days=5),
                "target": RoomStopSell.Status.CANCELLED,
            },
        )
        stop_sells = []
        for spec in scenarios:
            reason = f"[DEMO:{spec['marker']}] Tình huống mẫu cho kiểm thử vận hành."
            stop_sell = RoomStopSell.objects.filter(reason=reason).first()
            if stop_sell is None:
                stop_sell, _affected_count = create_room_stop_sell(
                    users["manager"],
                    {
                        "branch": spec["room"].branch,
                        "room": spec["room"],
                        "blocker": spec["blocker"],
                        "reason_code": spec["reason_code"],
                        "reason": reason,
                        "starts_at": spec["starts_at"],
                        "planned_end_at": spec["planned_end_at"],
                    },
                    DEMO_CONTEXT,
                )
            if (
                spec["target"] in {RoomStopSell.Status.REOPEN_REQUESTED, RoomStopSell.Status.ENDED}
                and stop_sell.status == RoomStopSell.Status.ACTIVE
            ):
                stop_sell = request_room_reopen(
                    users["manager"],
                    stop_sell.id,
                    stop_sell.version,
                    "[DEMO] Đã xử lý xong, đề nghị kiểm tra để mở bán lại.",
                    DEMO_CONTEXT,
                )
            if spec["target"] == RoomStopSell.Status.ENDED and stop_sell.status == RoomStopSell.Status.REOPEN_REQUESTED:
                stop_sell = confirm_room_reopen(
                    users["admin"],
                    stop_sell.id,
                    stop_sell.version,
                    "[DEMO] Đã kiểm tra thực tế và xác nhận phòng đủ điều kiện mở bán.",
                    DEMO_CONTEXT,
                )
            if spec["target"] == RoomStopSell.Status.CANCELLED and stop_sell.status == RoomStopSell.Status.ACTIVE:
                stop_sell = cancel_scheduled_stop_sell(
                    users["manager"],
                    stop_sell.id,
                    stop_sell.version,
                    "[DEMO] Kế hoạch tạm giữ phòng không còn cần thiết.",
                    DEMO_CONTEXT,
                )
            stop_sells.append(stop_sell)
        return stop_sells

    def _seed_photos_and_notifications(self, tasks, issues, users):
        photo_specs = (
            (
                tasks["TODAY"][HousekeepingTask.TaskType.CHECKIN_PREPARATION],
                TaskPhoto.Category.BEFORE,
                "DEMO-PHOTO-A202-BEFORE",
                "A202 — ảnh trước khi chuẩn bị phòng",
                None,
            ),
            (
                tasks["OCCUPIED"][HousekeepingTask.TaskType.CHECKIN_PREPARATION],
                TaskPhoto.Category.AFTER,
                "DEMO-PHOTO-A104-AFTER",
                "A104 — ảnh hoàn thành",
                None,
            ),
            (
                tasks["OCCUPIED"][HousekeepingTask.TaskType.CHECKIN_PREPARATION],
                TaskPhoto.Category.QC,
                "DEMO-PHOTO-A104-QC",
                "A104 — bằng chứng QC đạt",
                None,
            ),
            (
                tasks["AFFECTED"][HousekeepingTask.TaskType.CHECKIN_PREPARATION],
                TaskPhoto.Category.ISSUE,
                "DEMO-PHOTO-B303-ISSUE",
                "B303 — điều hòa rò nước",
                issues["active"],
            ),
        )
        for task, category, client_id, label, issue in photo_specs:
            self._ensure_demo_photo(task, category, client_id, label, users, issue)

        risk_task = tasks["TODAY"][HousekeepingTask.TaskType.CHECKIN_PREPARATION]
        notification, _ = Notification.objects.get_or_create(
            notification_type="DEMO_CHECKIN_RISK",
            object_type="HOUSEKEEPING_TASK",
            object_id=str(risk_task.id),
            defaults={
                "branch": risk_task.branch,
                "task": risk_task,
                "title": "[DEMO] Phòng A202 có nguy cơ trễ check-in",
                "body": "Task chuẩn bị phòng đang thực hiện và khách sẽ đến trong vài giờ.",
                "payload": {"source": "DEMO_SCENARIO", "taskId": str(risk_task.id)},
            },
        )
        for username in ("manager", "housekeeping_lead", "sales"):
            NotificationRecipient.objects.get_or_create(
                notification=notification,
                user=users[username],
            )

    def _ensure_demo_photo(self, task, category, client_id, label, users, issue=None):
        if TaskPhoto.objects.filter(task=task, client_id=client_id).exists():
            return
        color = {
            TaskPhoto.Category.BEFORE: "#b45309",
            TaskPhoto.Category.AFTER: "#047857",
            TaskPhoto.Category.QC: "#1d4ed8",
            TaskPhoto.Category.ISSUE: "#b91c1c",
        }.get(category, "#334155")
        safe_label = (
            label.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="540" '
            'viewBox="0 0 960 540">'
            f'<rect width="960" height="540" fill="{color}"/>'
            '<rect x="44" y="44" width="872" height="452" rx="28" '
            'fill="#ffffff" fill-opacity="0.12" stroke="#ffffff" stroke-width="3"/>'
            '<text x="480" y="235" text-anchor="middle" fill="#ffffff" '
            'font-family="Arial, sans-serif" font-size="34" font-weight="700">'
            f'{safe_label}</text>'
            '<text x="480" y="300" text-anchor="middle" fill="#ffffff" '
            'font-family="Arial, sans-serif" font-size="24">DỮ LIỆU MINH HỌA</text>'
            '<text x="480" y="350" text-anchor="middle" fill="#ffffff" '
            'font-family="Arial, sans-serif" font-size="20">Bliss Home Operations</text>'
            '</svg>'
        )
        # Prefixing a harmless base64 round-trip keeps the file creation path
        # binary-safe on both Python 3.9 and newer runtimes.
        image_content = base64.b64decode(base64.b64encode(svg.encode("utf-8")))
        photo = TaskPhoto(
            task=task,
            room=task.room,
            issue=issue,
            uploaded_by=users["housekeeping"],
            category=category,
            synced=True,
            sync_status=TaskPhoto.SyncStatus.SYNCED,
            source=TaskPhoto.Source.CAMERA,
            client_id=client_id,
            checksum=f"demo-{client_id.lower()}",
            captured_at=timezone.now(),
            device_id="demo-camera",
            metadata={"source": "DEMO_SCENARIO", "label": label},
        )
        photo.image.save(
            f"{client_id.lower()}.svg",
            ContentFile(image_content),
            save=False,
        )
        photo.save()
