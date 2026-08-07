import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def default_escalation_minutes():
    return [5, 15, 30]


class Branch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=500, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="owned_branches",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "branches"
        ordering = ["name"]

    def __str__(self):
        return f"{self.code} - {self.name}"


class BranchOwnershipHistory(models.Model):
    class Source(models.TextChoices):
        CREATED = "CREATED", "Tạo chi nhánh"
        TRANSFERRED = "TRANSFERRED", "Chuyển chủ"
        LEGACY_BACKFILL = "LEGACY_BACKFILL", "Chuẩn hóa dữ liệu cũ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="ownership_history")
    previous_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_branch_ownership_records",
    )
    new_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="new_branch_ownership_records",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branch_ownership_changes",
    )
    source = models.CharField(max_length=24, choices=Source.choices)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "branch_ownership_history"
        ordering = ["-created_at", "-id"]


class BranchHousekeepingPolicy(models.Model):
    branch = models.OneToOneField(Branch, on_delete=models.CASCADE, related_name="housekeeping_policy")
    allow_work_outside_shift = models.BooleanField(default=False)
    allow_return_after_start = models.BooleanField(default=False)
    allow_parallel_room_tasks = models.BooleanField(default=False)
    require_guest_consent = models.BooleanField(default=True)
    require_qr_verification = models.BooleanField(default=False)
    require_gps_verification = models.BooleanField(default=False)
    require_wifi_verification = models.BooleanField(default=False)
    require_camera_verification = models.BooleanField(default=False)
    require_direct_camera_for_evidence = models.BooleanField(default=False)
    block_completion_with_pending_sync = models.BooleanField(default=True)
    block_completion_with_pending_supply = models.BooleanField(default=True)
    rework_failed_items_only = models.BooleanField(default=True)
    concurrent_task_limit = models.PositiveSmallIntegerField(default=3)
    checkin_risk_buffer_minutes = models.PositiveSmallIntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_branch_policies"


class Area(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="areas")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    floor_label = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "housekeeping_areas"
        ordering = ["branch__name", "name"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_branch_area_code")]

    def __str__(self):
        return f"{self.branch.code} - {self.name}"


class Skill(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="housekeeping_skills")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "housekeeping_skills"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_branch_skill_code")]

    def __str__(self):
        return self.name


class HousekeepingTeam(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="housekeeping_teams")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="led_housekeeping_teams",
    )
    areas = models.ManyToManyField(Area, blank=True, related_name="teams")
    required_skills = models.ManyToManyField(Skill, blank=True, related_name="teams")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "housekeeping_teams"
        ordering = ["branch__name", "name"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_branch_team_code")]

    def __str__(self):
        return f"{self.branch.code} - {self.name}"


class BranchMembership(models.Model):
    class MembershipRole(models.TextChoices):
        HOUSEKEEPER = "HOUSEKEEPER", "Nhân viên buồng phòng"
        HOUSEKEEPING_LEAD = "HOUSEKEEPING_LEAD", "Trưởng nhóm buồng phòng"
        MANAGER = "MANAGER", "Quản lý"
        QC = "QC", "Kiểm tra chất lượng"
        WAREHOUSE = "WAREHOUSE", "Kho"
        TECHNICIAN = "TECHNICIAN", "Kỹ thuật"
        SALES = "SALES", "Kinh doanh"
        VIEWER = "VIEWER", "Chỉ xem"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="branch_memberships")
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="memberships")
    is_active = models.BooleanField(default=True)
    can_work_outside_shift = models.BooleanField(default=False)
    can_manage_team = models.BooleanField(default=False)
    area = models.CharField(max_length=100, blank=True)
    membership_role = models.CharField(
        max_length=24,
        choices=MembershipRole.choices,
        default=MembershipRole.HOUSEKEEPER,
        db_index=True,
    )
    team = models.ForeignKey(
        HousekeepingTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="memberships",
    )
    areas = models.ManyToManyField(Area, blank=True, related_name="memberships")
    skills = models.ManyToManyField(Skill, blank=True, related_name="memberships")

    class Meta:
        db_table = "branch_memberships"
        constraints = [models.UniqueConstraint(fields=("user", "branch"), name="unique_user_branch")]


class Shift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="shifts")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=100)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "shifts"
        ordering = ["starts_at"]
        constraints = [models.UniqueConstraint(fields=("branch", "code", "starts_at"), name="unique_branch_shift_instance")]

    def contains(self, moment=None):
        moment = moment or timezone.now()
        return self.is_active and self.starts_at <= moment <= self.ends_at

    def __str__(self):
        return f"{self.branch.code} - {self.name}"


class ShiftAssignment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="housekeeping_shift_assignments")
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, related_name="assignments")
    team = models.ForeignKey(HousekeepingTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name="shift_assignments")
    areas = models.ManyToManyField(Area, blank=True, related_name="shift_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_housekeeping_shift_assignments",
    )
    is_overtime = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_shift_assignments"
        constraints = [models.UniqueConstraint(fields=("user", "shift"), name="unique_user_shift_assignment")]


class Room(models.Model):
    class Status(models.TextChoices):
        READY = "READY", "Sẵn sàng"
        DIRTY = "DIRTY", "Bẩn"
        WAITING_CLEANING = "WAITING_CLEANING", "Chờ dọn"
        CLEANING = "CLEANING", "Đang dọn"
        CLEANING_BLOCKED = "CLEANING_BLOCKED", "Dọn phòng bị chặn"
        WAITING_QC = "WAITING_QC", "Chờ kiểm tra chất lượng"
        REWORK_REQUIRED = "REWORK_REQUIRED", "Cần làm lại"
        OUT_OF_SERVICE = "OUT_OF_SERVICE", "Ngừng phục vụ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="rooms")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    floor = models.CharField(max_length=50, blank=True)
    area = models.CharField(max_length=100, blank=True)
    area_ref = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name="rooms")
    room_type = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.READY, db_index=True)
    qr_identifier_hash = models.CharField(max_length=128, blank=True, db_index=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    verification_radius_meters = models.PositiveIntegerField(default=100)
    allowed_wifi_identifiers = models.JSONField(default=list, blank=True)
    is_guest_occupied = models.BooleanField(default=False)
    is_locked = models.BooleanField(default=False)
    operational_note = models.TextField(blank=True)

    class Meta:
        db_table = "rooms"
        ordering = ["branch__name", "code"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_room_code_in_branch")]

    def __str__(self):
        return f"{self.branch.code}/{self.code}"


class Booking(models.Model):
    class Status(models.TextChoices):
        BOOKED = "BOOKED", "Đã đặt"
        CHECKED_IN = "CHECKED_IN", "Đã nhận phòng"
        CHECKED_OUT = "CHECKED_OUT", "Đã trả phòng"
        CANCELLED = "CANCELLED", "Đã hủy"

    class Source(models.TextChoices):
        MANUAL_SALES = "MANUAL_SALES", "Nhân viên kinh doanh nhập"
        IMPORT = "IMPORT", "Nhập từ tệp"
        PMS = "PMS", "Đồng bộ PMS"
        LEGACY = "LEGACY", "Dữ liệu cũ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="bookings")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="bookings")
    code = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOOKED, db_index=True)
    checkin_at = models.DateTimeField(null=True, blank=True, db_index=True)
    checkout_at = models.DateTimeField(null=True, blank=True, db_index=True)
    guest_name = models.CharField(max_length=200, blank=True)
    guest_phone = models.CharField(max_length=30, blank=True)
    guest_count = models.PositiveSmallIntegerField(default=1)
    special_requests = models.TextField(blank=True)
    room_charge = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Tổng tiền phòng của cả kỳ lưu trú.",
    )
    service_charge = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Phụ thu và dịch vụ tính thêm cho booking.",
    )
    discount_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Tổng số tiền giảm giá của booking.",
    )
    paid_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        help_text="Tổng số tiền khách đã thanh toán.",
    )
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.MANUAL_SALES,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bookings",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_bookings",
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_bookings",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_bookings"
        ordering = ["-checkin_at", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=("branch", "code"),
                name="unique_branch_booking_code",
            ),
            models.CheckConstraint(
                check=(
                    models.Q(room_charge__gte=0)
                    & models.Q(service_charge__gte=0)
                    & models.Q(discount_amount__gte=0)
                    & models.Q(paid_amount__gte=0)
                ),
                name="booking_money_values_nonneg",
            ),
            models.CheckConstraint(
                check=models.Q(
                    discount_amount__lte=models.F("room_charge")
                    + models.F("service_charge")
                ),
                name="booking_discount_within_total",
            ),
            models.CheckConstraint(
                check=models.Q(
                    paid_amount__lte=models.F("room_charge")
                    + models.F("service_charge")
                    - models.F("discount_amount")
                ),
                name="booking_paid_within_total",
            ),
        ]

    @property
    def total_amount(self):
        return self.room_charge + self.service_charge - self.discount_amount

    @property
    def outstanding_amount(self):
        return self.total_amount - self.paid_amount

    def __str__(self):
        return f"{self.code} - {self.room}"


class CapitalEntry(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="capital_entries",
    )
    title = models.CharField(max_length=180)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    capital_date = models.DateField(default=timezone.localdate, db_index=True)
    source = models.CharField(max_length=180, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_capital_entries",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_capital_entries",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_capital_entries"
        ordering = ["-capital_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="capital_entry_amount_nonneg",
            ),
        ]
        indexes = [models.Index(fields=("branch", "capital_date"), name="capital_branch_date_idx")]

    def __str__(self):
        return f"{self.title} - {self.capital_date:%d/%m/%Y}"


class OperatingExpense(models.Model):
    class PaymentStatus(models.TextChoices):
        PLANNED = "PLANNED", "Dự kiến"
        PAID = "PAID", "Đã chi"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="operating_expenses",
    )
    name = models.CharField(max_length=180)
    category = models.CharField(max_length=100, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    payment_status = models.CharField(
        max_length=10,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PAID,
        db_index=True,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_operating_expenses",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_operating_expenses",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_operating_expenses"
        ordering = ["-expense_date", "-created_at"]
        constraints = [
            models.CheckConstraint(
                check=models.Q(amount__gte=0),
                name="operating_expense_amount_nonneg",
            ),
        ]
        indexes = [models.Index(fields=("branch", "expense_date"), name="expense_branch_date_idx")]

    def __str__(self):
        return f"{self.name} - {self.expense_date:%d/%m/%Y}"


class BookingSpecialRequest(models.Model):
    class RequestType(models.TextChoices):
        BEDDING = "BEDDING", "Giường và đồ vải"
        AMENITY = "AMENITY", "Tiện nghi và vật tư"
        ARRIVAL = "ARRIVAL", "Nhận phòng và đón khách"
        ACCESSIBILITY = "ACCESSIBILITY", "Hỗ trợ tiếp cận"
        HOUSEKEEPING = "HOUSEKEEPING", "Vệ sinh và buồng phòng"
        CELEBRATION = "CELEBRATION", "Trang trí và dịp đặc biệt"
        OTHER = "OTHER", "Yêu cầu khác"

    class AppliesTo(models.TextChoices):
        CHECKIN = "CHECKIN", "Trước khi nhận phòng"
        STAY = "STAY", "Trong thời gian lưu trú"
        CHECKOUT = "CHECKOUT", "Khi trả phòng"
        ALL = "ALL", "Toàn bộ kỳ ở"

    class Priority(models.TextChoices):
        NORMAL = "NORMAL", "Bình thường"
        HIGH = "HIGH", "Ưu tiên cao"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="booking_special_requests",
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.CASCADE,
        related_name="special_request_items",
    )
    request_type = models.CharField(
        max_length=24,
        choices=RequestType.choices,
        default=RequestType.OTHER,
        db_index=True,
    )
    applies_to = models.CharField(
        max_length=16,
        choices=AppliesTo.choices,
        default=AppliesTo.CHECKIN,
        db_index=True,
    )
    priority = models.CharField(
        max_length=12,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    description = models.CharField(max_length=500)
    quantity = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_booking_special_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_booking_special_requests"
        ordering = ["sort_order", "created_at", "id"]
        indexes = [
            models.Index(
                fields=("branch", "booking", "applies_to"),
                name="hk_booking_req_scope_idx",
            )
        ]

    def __str__(self):
        return self.description


class GuestServiceRequest(models.Model):
    """A request raised by an in-house guest and dispatched to field staff."""

    class RequestType(models.TextChoices):
        WATER = "WATER", "Nước uống"
        TOWEL = "TOWEL", "Khăn"
        AMENITY = "AMENITY", "Đồ dùng trong phòng"
        HOUSEKEEPING = "HOUSEKEEPING", "Dọn phòng theo yêu cầu"
        MAINTENANCE = "MAINTENANCE", "Hỗ trợ thiết bị"
        OTHER = "OTHER", "Yêu cầu khác"

    class Source(models.TextChoices):
        ZALO = "ZALO", "Zalo"
        PHONE = "PHONE", "Điện thoại"
        FRONT_DESK = "FRONT_DESK", "Lễ tân"
        OTHER = "OTHER", "Kênh khác"

    class Priority(models.TextChoices):
        LOW = "LOW", "Thấp"
        NORMAL = "NORMAL", "Bình thường"
        HIGH = "HIGH", "Cao"
        URGENT = "URGENT", "Khẩn cấp"

    class Status(models.TextChoices):
        NEW = "NEW", "Chờ tiếp nhận"
        ASSIGNED = "ASSIGNED", "Đã phân công"
        ACCEPTED = "ACCEPTED", "Đã nhận việc"
        IN_PROGRESS = "IN_PROGRESS", "Đang thực hiện"
        COMPLETED = "COMPLETED", "Đã giao khách"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="guest_service_requests",
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.PROTECT,
        related_name="guest_service_requests",
    )
    booking = models.ForeignKey(
        Booking,
        on_delete=models.PROTECT,
        related_name="guest_service_requests",
    )
    request_type = models.CharField(
        max_length=24,
        choices=RequestType.choices,
        db_index=True,
    )
    description = models.CharField(max_length=500)
    quantity = models.PositiveSmallIntegerField(default=1)
    unit = models.CharField(max_length=30, blank=True)
    source = models.CharField(
        max_length=20,
        choices=Source.choices,
        default=Source.ZALO,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        db_index=True,
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_guest_service_requests",
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_guest_service_requests",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispatched_guest_service_requests",
    )
    due_at = models.DateTimeField(db_index=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    resolution_note = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_guest_service_requests"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=("branch", "status", "due_at"),
                name="hk_guest_req_queue_idx",
            ),
            models.Index(
                fields=("assignee", "status"),
                name="hk_guest_req_worker_idx",
            ),
        ]

    @property
    def is_overdue(self):
        return bool(
            self.status not in {self.Status.COMPLETED, self.Status.CANCELLED}
            and self.due_at < timezone.now()
        )

    def __str__(self):
        return f"{self.code} - {self.room}"


class GuestServiceRequestEvent(models.Model):
    request = models.ForeignKey(
        GuestServiceRequest,
        on_delete=models.CASCADE,
        related_name="events",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    action = models.CharField(max_length=40, db_index=True)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    note = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "housekeeping_guest_service_request_events"
        ordering = ["created_at", "id"]


class BookingChangeLog(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Tạo booking"
        CHANGED = "CHANGED", "Thay đổi booking"
        CANCELLED = "CANCELLED", "Hủy booking"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="change_logs")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="booking_change_logs")
    action = models.CharField(max_length=20, choices=Action.choices, db_index=True)
    booking_version = models.PositiveIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="booking_changes",
    )
    reason = models.TextField(blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "housekeeping_booking_change_logs"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("booking", "booking_version", "action"),
                name="unique_booking_version_action",
            )
        ]


class ChecklistTemplate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="checklist_templates")
    code = models.CharField(max_length=80)
    name = models.CharField(max_length=180)
    task_type = models.CharField(max_length=30, blank=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_checklist_templates"
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_branch_checklist_tpl")]

    def __str__(self):
        return self.name


class ChecklistVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Nháp"
        PUBLISHED = "PUBLISHED", "Đã phát hành"
        RETIRED = "RETIRED", "Ngừng sử dụng"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template = models.ForeignKey(ChecklistTemplate, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField(default=1)
    version_label = models.CharField(max_length=30, default="v1")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_housekeeping_checklist_versions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_checklist_versions"
        ordering = ["template", "version_number"]
        constraints = [
            models.UniqueConstraint(fields=("template", "version_number"), name="unique_checklist_tpl_number"),
            models.UniqueConstraint(fields=("template", "version_label"), name="unique_checklist_tpl_label"),
        ]

    def __str__(self):
        return f"{self.template.name} {self.version_label}"


class ChecklistItemDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.ForeignKey(ChecklistVersion, on_delete=models.CASCADE, related_name="item_definitions")
    key = models.CharField(max_length=80)
    group_name = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=255)
    item_type = models.CharField(max_length=20, default="CHECKBOX")
    is_required = models.BooleanField(default=True)
    required_photo_count = models.PositiveSmallIntegerField(default=0)
    options = models.JSONField(default=list, blank=True)
    validation_rules = models.JSONField(default=dict, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "housekeeping_checklist_definitions"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=("version", "key"), name="unique_checklist_version_key")]

    def __str__(self):
        return self.title


class HousekeepingTask(models.Model):
    class TaskType(models.TextChoices):
        CHECKOUT_CLEANING = "CHECKOUT_CLEANING", "Dọn phòng sau khi khách trả phòng"
        STAYOVER_CLEANING = "STAYOVER_CLEANING", "Dọn phòng đang có khách"
        CHECKIN_PREPARATION = "CHECKIN_PREPARATION", "Chuẩn bị phòng đón khách"
        DEEP_CLEANING = "DEEP_CLEANING", "Vệ sinh chuyên sâu"
        QC_REWORK = "QC_REWORK", "Dọn lại sau kiểm tra chất lượng"
        PERIODIC_CLEANING = "PERIODIC_CLEANING", "Vệ sinh định kỳ"

    class Priority(models.TextChoices):
        LOW = "LOW", "Thấp"
        NORMAL = "NORMAL", "Bình thường"
        HIGH = "HIGH", "Cao"
        URGENT = "URGENT", "Khẩn cấp"

    class Status(models.TextChoices):
        UNASSIGNED = "UNASSIGNED", "Chờ phân công"
        ASSIGNED = "ASSIGNED", "Đã phân công"
        PENDING_ACCEPTANCE = "PENDING_ACCEPTANCE", "Chờ nhận việc"
        ACCEPTED = "ACCEPTED", "Đã nhận việc"
        IN_PROGRESS = "IN_PROGRESS", "Đang thực hiện"
        PAUSED = "PAUSED", "Tạm dừng"
        WAITING_SUPPORT = "WAITING_SUPPORT", "Chờ hỗ trợ"
        COMPLETED = "COMPLETED", "Đã hoàn thành"
        WAITING_QC = "WAITING_QC", "Chờ kiểm tra chất lượng"
        QC_REJECTED = "QC_REJECTED", "Kiểm tra không đạt"
        QC_APPROVED = "QC_APPROVED", "Kiểm tra đạt"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="housekeeping_tasks")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="housekeeping_tasks")
    booking_code = models.CharField(max_length=50, blank=True, db_index=True)
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="housekeeping_tasks")
    task_type = models.CharField(max_length=30, choices=TaskType.choices)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL, db_index=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.UNASSIGNED, db_index=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_housekeeping_tasks")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_housekeeping_tasks_by_me",
    )
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    team = models.ForeignKey(HousekeepingTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    required_skills = models.ManyToManyField(
        Skill,
        blank=True,
        related_name="required_by_tasks",
    )
    checklist_version = models.CharField(max_length=30, default="v1")
    checklist_template_version = models.ForeignKey(
        ChecklistVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="tasks",
    )
    scheduled_start_at = models.DateTimeField()
    acceptance_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    start_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    due_at = models.DateTimeField(db_index=True)
    standard_duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    next_checkin_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    last_progress_at = models.DateTimeField(null=True, blank=True, db_index=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_housekeeping_tasks",
    )
    pause_reason = models.CharField(max_length=50, blank=True)
    rework_count = models.PositiveSmallIntegerField(default=0)
    rework_started_at = models.DateTimeField(null=True, blank=True)
    current_rework_round = models.PositiveSmallIntegerField(default=0)
    requires_qc = models.BooleanField(default=True)
    locked_by_manager = models.BooleanField(default=False)
    guest_in_room = models.BooleanField(default=False)
    special_request = models.TextField(blank=True)
    special_request_items = models.JSONField(default=list, blank=True)
    note = models.TextField(blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_housekeeping_tasks",
    )
    cancellation_reason = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="created_housekeeping_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_tasks"
        ordering = ["due_at", "-priority", "code"]
        indexes = [
            models.Index(fields=("branch", "status", "due_at"), name="hk_task_scope_idx"),
            models.Index(fields=("shift", "status", "scheduled_start_at"), name="hk_shift_status_idx"),
            models.Index(fields=("assignee", "status", "due_at"), name="hk_assignee_status_idx"),
            models.Index(fields=("room", "status"), name="hk_room_status_idx"),
        ]

    @property
    def is_overdue(self):
        return self.status not in {self.Status.QC_APPROVED, self.Status.CANCELLED} and self.due_at < timezone.now()

    def __str__(self):
        return f"{self.code} - {self.room.code}"


class TaskAssignment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ nhận"
        ACCEPTED = "ACCEPTED", "Đã nhận"
        REJECTED = "REJECTED", "Đã từ chối"
        RETURNED = "RETURNED", "Đã trả"
        REASSIGNED = "REASSIGNED", "Đã điều chuyển"
        ENDED = "ENDED", "Đã kết thúc"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="assignments")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="housekeeping_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_assignments_created",
    )
    shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_assignments")
    team = models.ForeignKey(HousekeepingTeam, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_assignments")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    is_current = models.BooleanField(default=True, db_index=True)
    reason_code = models.CharField(max_length=50, blank=True)
    note = models.TextField(blank=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "housekeeping_task_assignments"
        ordering = ["assigned_at", "id"]
        indexes = [models.Index(fields=("assignee", "is_current", "status"), name="hk_assign_user_idx")]


class TaskHandover(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="handovers")
    from_assignment = models.ForeignKey(
        TaskAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_handovers",
    )
    to_assignment = models.ForeignKey(
        TaskAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_handovers",
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_handovers_sent",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="housekeeping_handovers_received",
    )
    from_shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="outgoing_handovers")
    to_shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, related_name="incoming_handovers")
    note = models.TextField(blank=True)
    reconfirm_required_items = models.JSONField(default=list, blank=True)
    handed_over_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="housekeeping_handovers_created",
    )
    handed_over_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_task_handovers"
        ordering = ["handed_over_at", "id"]


class TaskRoomVerification(models.Model):
    class Method(models.TextChoices):
        QR_CODE = "QR_CODE", "QR phòng"
        GPS = "GPS", "GPS"
        WIFI = "WIFI", "Wi-Fi"
        CAMERA = "CAMERA", "Ảnh chụp trực tiếp"
        MANAGER_OVERRIDE = "MANAGER_OVERRIDE", "Quản lý xác nhận"
        GUEST_CONSENT = "GUEST_CONSENT", "Khách đồng ý"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="room_verifications")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="room_verifications")
    method = models.CharField(max_length=30, choices=Method.choices)
    submitted_value_hash = models.CharField(max_length=128, blank=True)
    server_reference = models.CharField(max_length=255, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    wifi_identifier = models.CharField(max_length=255, blank=True)
    guest_consent_confirmed = models.BooleanField(default=False)
    guest_consent_note = models.TextField(blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    successful = models.BooleanField(default=False, db_index=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    verified_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        db_table = "housekeeping_room_verifications"
        ordering = ["verified_at", "id"]


class TaskChecklistItem(models.Model):
    class ItemType(models.TextChoices):
        CHECKBOX = "CHECKBOX", "Ô đánh dấu"
        YES_NO = "YES_NO", "Có/không"
        NUMBER = "NUMBER", "Số lượng"
        TEXT = "TEXT", "Văn bản"
        PHOTO = "PHOTO", "Chụp ảnh"
        SINGLE_SELECT = "SINGLE_SELECT", "Chọn một"
        MULTI_SELECT = "MULTI_SELECT", "Chọn nhiều"
        DEVICE_CHECK = "DEVICE_CHECK", "Kiểm tra thiết bị"
        QR_SCAN = "QR_SCAN", "Quét mã QR"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Chưa xử lý"
        COMPLETED = "COMPLETED", "Hoàn thành"
        FAILED = "FAILED", "Không đạt"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="checklist_items")
    definition = models.ForeignKey(
        ChecklistItemDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task_snapshots",
    )
    definition_key = models.CharField(max_length=80)
    group_name = models.CharField(max_length=100, blank=True)
    title = models.CharField(max_length=255)
    item_type = models.CharField(max_length=20, choices=ItemType.choices, default=ItemType.CHECKBOX)
    is_required = models.BooleanField(default=True)
    requires_photo = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    value = models.JSONField(null=True, blank=True)
    options_snapshot = models.JSONField(default=list, blank=True)
    validation_snapshot = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)
    failure_issue = models.ForeignKey(
        "IssueTicket",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_checklist_failures",
    )
    failure_accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accepted_checklist_failures",
    )
    failure_accepted_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    update_version = models.PositiveIntegerField(default=1)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "housekeeping_task_checklist_items"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=("task", "definition_key"), name="unique_task_checklist_definition")]


class TaskPhoto(models.Model):
    class Category(models.TextChoices):
        BEFORE = "BEFORE", "Trước khi dọn"
        AFTER = "AFTER", "Sau khi dọn"
        ISSUE = "ISSUE", "Sự cố"
        SUPPLY = "SUPPLY", "Thiếu vật tư"
        QC = "QC", "Kiểm tra chất lượng"
        AREA = "AREA", "Khu vực"
        EVIDENCE = "EVIDENCE", "Bằng chứng hoàn thành"

    class Source(models.TextChoices):
        CAMERA = "CAMERA", "Máy ảnh"
        GALLERY = "GALLERY", "Thư viện"
        OFFLINE_CAMERA = "OFFLINE_CAMERA", "Máy ảnh ngoại tuyến"

    class SyncStatus(models.TextChoices):
        PENDING = "PENDING", "Chờ đồng bộ"
        SYNCED = "SYNCED", "Đã đồng bộ"
        FAILED = "FAILED", "Đồng bộ lỗi"
        CONFLICT = "CONFLICT", "Xung đột"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="photos")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, null=True, blank=True, related_name="housekeeping_photos")
    checklist_item = models.ForeignKey(TaskChecklistItem, on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    issue = models.ForeignKey("IssueTicket", on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    supply_request = models.ForeignKey("SupplyRequest", on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    qc_round = models.ForeignKey("QCTask", on_delete=models.SET_NULL, null=True, blank=True, related_name="photos")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    image = models.ImageField(upload_to="housekeeping/%Y/%m/%d/")
    synced = models.BooleanField(default=True)
    sync_status = models.CharField(max_length=20, choices=SyncStatus.choices, default=SyncStatus.SYNCED, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.CAMERA)
    client_id = models.CharField(max_length=64, blank=True, db_index=True)
    checksum = models.CharField(max_length=64, blank=True, db_index=True)
    captured_at = models.DateTimeField(null=True, blank=True, db_index=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    accuracy_meters = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_task_photos"
        constraints = [
            models.UniqueConstraint(
                fields=("task", "client_id"),
                condition=~models.Q(client_id=""),
                name="unique_task_photo_client_id",
            )
        ]


class TaskPause(models.Model):
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="pauses")
    previous_status = models.CharField(max_length=30, blank=True)
    reason_code = models.CharField(max_length=50)
    note = models.TextField(blank=True)
    excluded_from_sla = models.BooleanField(default=False)
    paused_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="task_pauses")
    paused_at = models.DateTimeField(auto_now_add=True)
    resumed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_resumes")
    resumed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_task_pauses",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "housekeeping_task_pauses"


class SupplyLocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="supply_locations")
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=150)
    notification_role = models.CharField(max_length=32, default="warehouse")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "housekeeping_supply_locations"
        ordering = ["branch__name", "name"]
        constraints = [models.UniqueConstraint(fields=("branch", "code"), name="unique_branch_supply_loc")]

    def __str__(self):
        return f"{self.branch.code} - {self.name}"


class SupplyRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ xử lý"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Đã tiếp nhận"
        FULFILLED = "FULFILLED", "Đã cấp"
        REJECTED = "REJECTED", "Từ chối"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="supply_requests")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    destination = models.ForeignKey(SupplyLocation, on_delete=models.PROTECT, null=True, blank=True, related_name="requests")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    priority = models.CharField(max_length=10, choices=HousekeepingTask.Priority.choices, default=HousekeepingTask.Priority.NORMAL)
    note = models.TextField(blank=True)
    warehouse = models.CharField(max_length=150, blank=True)
    blocks_completion = models.BooleanField(default=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    version = models.PositiveIntegerField(default=1)
    client_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_supply_requests",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        db_table = "housekeeping_supply_requests"
        constraints = [
            models.UniqueConstraint(
                fields=("task", "requested_by", "client_request_id"),
                condition=~models.Q(client_request_id=""),
                name="unique_supply_request_client_id",
            )
        ]


class SupplyRequestItem(models.Model):
    request = models.ForeignKey(SupplyRequest, on_delete=models.CASCADE, related_name="items")
    inventory_item_id = models.CharField(max_length=80)
    item_name = models.CharField(max_length=150, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=30)

    class Meta:
        db_table = "housekeeping_supply_request_items"


class IssueTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Đang mở"
        ASSIGNED = "ASSIGNED", "Đã phân công"
        IN_PROGRESS = "IN_PROGRESS", "Đang xử lý"
        RESOLVED = "RESOLVED", "Đã xử lý"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="issues")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="issues")
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name="issues")
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_housekeeping_issues",
    )
    device_id = models.CharField(max_length=80, blank=True)
    issue_type = models.CharField(max_length=80)
    severity = models.CharField(max_length=10, choices=HousekeepingTask.Priority.choices)
    description = models.TextField()
    blocks_room_ready = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    version = models.PositiveIntegerField(default=1)
    client_request_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_housekeeping_issues",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)

    class Meta:
        db_table = "housekeeping_issue_tickets"
        constraints = [
            models.UniqueConstraint(
                fields=("task", "reported_by", "client_request_id"),
                condition=~models.Q(client_request_id=""),
                name="unique_issue_client_id",
            )
        ]


class QCTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ kiểm tra chất lượng"
        APPROVED = "APPROVED", "Đạt"
        REJECTED = "REJECTED", "Không đạt"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="qc_rounds")
    round_number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    reason = models.TextField(blank=True)
    note = models.TextField(blank=True)
    checklist_snapshot = models.JSONField(default=list, blank=True)
    result_snapshot = models.JSONField(default=dict, blank=True)
    deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "housekeeping_qc_tasks"
        ordering = ["round_number"]
        constraints = [models.UniqueConstraint(fields=("task", "round_number"), name="unique_task_qc_round")]


class ReworkRound(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Chờ làm lại"
        IN_PROGRESS = "IN_PROGRESS", "Đang làm lại"
        SENT_TO_QC = "SENT_TO_QC", "Đã gửi kiểm tra chất lượng"
        COMPLETED = "COMPLETED", "Hoàn tất"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="rework_rounds")
    source_qc_round = models.ForeignKey(QCTask, on_delete=models.PROTECT, related_name="rework_rounds")
    round_number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    failed_items_only = models.BooleanField(default=True)
    checklist_snapshot = models.JSONField(default=list, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_housekeeping_reworks",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    sent_to_qc_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_rework_rounds"
        ordering = ["round_number"]
        constraints = [models.UniqueConstraint(fields=("task", "round_number"), name="unique_task_rework_round")]


class QCFailedItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    qc_round = models.ForeignKey(QCTask, on_delete=models.CASCADE, related_name="failed_items")
    checklist_item = models.ForeignKey(TaskChecklistItem, on_delete=models.PROTECT, related_name="qc_failures")
    reason_code = models.CharField(max_length=50, blank=True)
    reason = models.TextField()
    note = models.TextField(blank=True)
    rework_required = models.BooleanField(default=True)
    resolved_in_rework = models.ForeignKey(
        ReworkRound,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_failed_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_qc_failed_items"
        constraints = [models.UniqueConstraint(fields=("qc_round", "checklist_item"), name="unique_qc_failed_item")]


class TaskStatusHistory(models.Model):
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    reason_code = models.CharField(max_length=50, blank=True)
    note = models.TextField(blank=True)
    task_version = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "task_status_history"
        ordering = ["changed_at", "id"]


class HousekeepingActivityLog(models.Model):
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="activity_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT)
    action = models.CharField(max_length=50, db_index=True)
    reason_code = models.CharField(max_length=50, blank=True)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=80, blank=True, db_index=True)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "housekeeping_activity_logs"
        ordering = ["-created_at", "-id"]


class SLAPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="sla_policies")
    name = models.CharField(max_length=150)
    task_type = models.CharField(max_length=30, blank=True, db_index=True)
    priority = models.CharField(max_length=10, blank=True, db_index=True)
    acceptance_minutes = models.PositiveIntegerField(default=5)
    start_minutes = models.PositiveIntegerField(default=15)
    completion_minutes = models.PositiveIntegerField(default=45)
    checkin_risk_buffer_minutes = models.PositiveIntegerField(default=15)
    exclude_approved_pause_time = models.BooleanField(default=True)
    escalation_minutes = models.JSONField(default=default_escalation_minutes)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_sla_policies"
        ordering = ["branch__name", "name"]


class TaskSLAState(models.Model):
    task = models.OneToOneField(HousekeepingTask, on_delete=models.CASCADE, related_name="sla_state")
    policy = models.ForeignKey(SLAPolicy, on_delete=models.SET_NULL, null=True, blank=True, related_name="task_states")
    policy_snapshot = models.JSONField(default=dict, blank=True)
    acceptance_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    start_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    completion_due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    excluded_pause_seconds = models.PositiveIntegerField(default=0)
    acceptance_breached_at = models.DateTimeField(null=True, blank=True)
    start_breached_at = models.DateTimeField(null=True, blank=True)
    completion_breached_at = models.DateTimeField(null=True, blank=True)
    checkin_risk_at = models.DateTimeField(null=True, blank=True)
    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    legacy_backfill = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_task_sla_states"


class SLAEscalationEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, related_name="sla_escalations")
    event_type = models.CharField(max_length=40)
    threshold_minutes = models.PositiveIntegerField(default=0)
    recipient_role = models.CharField(max_length=32)
    occurred_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "housekeeping_sla_escalations"
        constraints = [
            models.UniqueConstraint(
                fields=("task", "event_type", "threshold_minutes", "recipient_role"),
                name="unique_task_sla_escalation",
            )
        ]


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    notification_type = models.CharField(max_length=50, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField()
    object_type = models.CharField(max_length=50, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "housekeeping_notifications"
        ordering = ["-created_at", "-id"]


class NotificationRecipient(models.Model):
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE, related_name="recipient_rows")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="housekeeping_notifications")
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "housekeeping_notification_recipients"
        constraints = [models.UniqueConstraint(fields=("notification", "user"), name="unique_notification_user")]
        indexes = [models.Index(fields=("user", "read_at"), name="hk_notice_user_idx")]


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=60, db_index=True)
    aggregate_type = models.CharField(max_length=50)
    aggregate_id = models.CharField(max_length=64)
    deduplication_key = models.CharField(max_length=120, unique=True)
    payload = models.JSONField(default=dict)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "housekeeping_outbox_events"
        ordering = ["available_at", "created_at"]


class OfflineMutationReceipt(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Đã nhận"
        SUCCEEDED = "SUCCEEDED", "Thành công"
        FAILED = "FAILED", "Thất bại"
        CONFLICT = "CONFLICT", "Xung đột"
        DISCARDED = "DISCARDED", "Đã bỏ thay đổi cục bộ"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="offline_mutation_receipts")
    task = models.ForeignKey(HousekeepingTask, on_delete=models.CASCADE, null=True, blank=True, related_name="offline_receipts")
    idempotency_key = models.CharField(max_length=80)
    client_mutation_id = models.CharField(max_length=80, blank=True, db_index=True)
    operation = models.CharField(max_length=60)
    payload_hash = models.CharField(max_length=64)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    base_version = models.PositiveIntegerField(null=True, blank=True)
    result_version = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    error_code = models.CharField(max_length=50, blank=True)
    depends_on = models.JSONField(default=list, blank=True)
    conflict_payload = models.JSONField(default=dict, blank=True)
    resolution = models.CharField(max_length=30, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "housekeeping_offline_receipts"
        constraints = [models.UniqueConstraint(fields=("user", "idempotency_key"), name="unique_user_idempotency_key")]
        indexes = [models.Index(fields=("task", "status", "created_at"), name="hk_receipt_task_idx")]
