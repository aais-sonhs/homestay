import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from housekeeping.models import Branch, IssueTicket, Room


class RoomBlocker(models.Model):
    class Kind(models.TextChoices):
        ISSUE = "ISSUE", "Sự cố"
        MAINTENANCE = "MAINTENANCE", "Bảo trì"
        CLEANLINESS = "CLEANLINESS", "Vệ sinh"
        SAFETY = "SAFETY", "An toàn"
        MANUAL = "MANUAL", "Quản lý chặn thủ công"
        OTHER = "OTHER", "Lý do khác"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Đang chặn"
        CLEARANCE_PENDING = "CLEARANCE_PENDING", "Chờ xác nhận gỡ chặn"
        CLEARED = "CLEARED", "Đã gỡ chặn"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="room_blockers")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="operational_blockers")
    issue = models.OneToOneField(
        IssueTicket,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="room_blocker",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    reason = models.CharField(max_length=500)
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    planned_end_at = models.DateTimeField(null=True, blank=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_room_blockers",
    )
    clearance_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_room_blocker_clearances",
    )
    clearance_requested_at = models.DateTimeField(null=True, blank=True)
    clearance_note = models.TextField(blank=True)
    cleared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cleared_room_blockers",
    )
    cleared_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "room_operations_blockers"
        ordering = ["-starts_at", "-created_at"]
        indexes = [
            models.Index(fields=("branch", "status", "starts_at"), name="room_blocker_scope_idx"),
            models.Index(fields=("room", "status"), name="room_blocker_room_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(planned_end_at__isnull=True)
                | models.Q(planned_end_at__gt=models.F("starts_at")),
                name="room_blocker_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.room.code}: {self.reason}"


class RoomBlockerHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Tạo blocker"
        CLEARANCE_REQUESTED = "CLEARANCE_REQUESTED", "Yêu cầu gỡ blocker"
        CLEARED = "CLEARED", "Xác nhận gỡ blocker"
        CANCELLED = "CANCELLED", "Hủy blocker"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    blocker = models.ForeignKey(RoomBlocker, on_delete=models.CASCADE, related_name="history")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="room_blocker_history")
    action = models.CharField(max_length=24, choices=Action.choices, db_index=True)
    blocker_version = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_blocker_history_entries",
    )
    note = models.TextField(blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "room_operations_blocker_history"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("blocker", "blocker_version", "action"),
                name="unique_room_blocker_version_action",
            )
        ]


class RoomStopSell(models.Model):
    class ReasonCode(models.TextChoices):
        MAINTENANCE = "MAINTENANCE", "Bảo trì hoặc sửa chữa"
        SAFETY = "SAFETY", "An toàn"
        CLEANLINESS = "CLEANLINESS", "Vệ sinh chưa đạt"
        OWNER_HOLD = "OWNER_HOLD", "Chủ chi nhánh tạm giữ phòng"
        GUEST_IMPACT = "GUEST_IMPACT", "Ảnh hưởng trải nghiệm khách"
        OTHER = "OTHER", "Lý do khác"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Đang dừng bán"
        REOPEN_REQUESTED = "REOPEN_REQUESTED", "Chờ xác nhận mở lại"
        ENDED = "ENDED", "Đã mở bán lại"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="room_stop_sells")
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name="stop_sells")
    blocker = models.ForeignKey(RoomBlocker, on_delete=models.PROTECT, related_name="stop_sells")
    reason_code = models.CharField(max_length=24, choices=ReasonCode.choices, db_index=True)
    reason = models.CharField(max_length=500)
    starts_at = models.DateTimeField(db_index=True)
    planned_end_at = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_room_stop_sells",
    )
    reopen_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_room_reopens",
    )
    reopen_requested_at = models.DateTimeField(null=True, blank=True)
    reopen_request_note = models.TextField(blank=True)
    reopened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="confirmed_room_reopens",
    )
    reopened_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reopen_confirmation_note = models.TextField(blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cancelled_room_stop_sells",
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "room_operations_stop_sells"
        ordering = ["-starts_at", "-created_at"]
        indexes = [
            models.Index(fields=("branch", "status", "starts_at"), name="stop_sell_scope_idx"),
            models.Index(fields=("room", "status", "starts_at"), name="stop_sell_room_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(planned_end_at__gt=models.F("starts_at")),
                name="stop_sell_end_after_start",
            )
        ]

    def __str__(self):
        return f"{self.room.code}: {self.get_status_display()}"


class RoomStopSellHistory(models.Model):
    class Action(models.TextChoices):
        CREATED = "CREATED", "Bắt đầu dừng bán"
        REOPEN_REQUESTED = "REOPEN_REQUESTED", "Yêu cầu mở bán lại"
        REOPEN_CONFIRMED = "REOPEN_CONFIRMED", "Xác nhận mở bán lại"
        CANCELLED = "CANCELLED", "Hủy lịch dừng bán"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stop_sell = models.ForeignKey(RoomStopSell, on_delete=models.CASCADE, related_name="history")
    branch = models.ForeignKey(Branch, on_delete=models.PROTECT, related_name="room_stop_sell_history")
    action = models.CharField(max_length=24, choices=Action.choices, db_index=True)
    stop_sell_version = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="room_stop_sell_history_entries",
    )
    note = models.TextField(blank=True)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "room_operations_stop_sell_history"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=("stop_sell", "stop_sell_version", "action"),
                name="unique_stop_sell_version_action",
            )
        ]
