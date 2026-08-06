import secrets
import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now
from .identifiers import normalize_email, normalize_phone


class User(AbstractUser):
    class Role(models.TextChoices):
        FOUNDER = "founder", "Nhà sáng lập / Quản trị viên"
        MANAGER = "manager", "Quản lý"
        HOUSEKEEPING = "housekeeping", "Nhân viên buồng phòng"
        QC = "qc", "Kiểm tra chất lượng"
        TECHNICIAN = "technician", "Kỹ thuật"
        WAREHOUSE = "warehouse", "Kho"
        CUSTOMER_SERVICE = "customer_service", "CSKH"

    role = models.CharField(max_length=32, choices=Role.choices, default=Role.HOUSEKEEPING)
    phone_number = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True)
    normalized_phone = models.CharField(max_length=16, blank=True, db_index=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    is_permanently_disabled = models.BooleanField(default=False)
    disabled_by_admin = models.BooleanField(default=False)
    locked_due_to_failed_logins = models.BooleanField(default=False)
    password_changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_unique_email_ci",
            ),
            models.UniqueConstraint(
                fields=["normalized_phone"],
                condition=~Q(normalized_phone=""),
                name="accounts_user_unique_normalized_phone",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.email:
            self.email = normalize_email(self.email)
        self.normalized_phone = normalize_phone(self.phone_number) if self.phone_number else ""
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name().strip() or self.username

    def delete(self, using=None, keep_parents=False):
        if self.is_deleted:
            return 0, {self._meta.label: 0}
        self.is_deleted = True
        self.is_active = False
        self.save(update_fields=["is_deleted", "is_active"])
        self.access_tokens.filter(revoked_at__isnull=True).update(revoked_at=Now())
        self.refresh_tokens.filter(revoked_at__isnull=True).update(revoked_at=Now())
        return 1, {self._meta.label: 1}

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)


class AccessToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="access_tokens")
    key = models.CharField(max_length=64, unique=True, editable=False)
    label = models.CharField(max_length=100, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "access_tokens"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_hex(32)
        super().save(*args, **kwargs)

    def revoke(self):
        if self.revoked_at is None:
            from django.utils import timezone

            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])


class RefreshToken(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refresh_tokens")
    key = models.CharField(max_length=128, unique=True, editable=False)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "refresh_tokens"

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = secrets.token_urlsafe(48)
        super().save(*args, **kwargs)

    def revoke(self):
        if self.revoked_at is None:
            from django.utils import timezone

            self.revoked_at = timezone.now()
            self.save(update_fields=["revoked_at"])


class PasswordHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_history")
    password_hash = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_histories"
        ordering = ["-created_at", "-id"]


class PasswordResetRequest(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Thư điện tử"
        SMS = "sms", "SMS"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Đang chờ"
        VERIFIED = "VERIFIED", "Đã xác thực"
        COMPLETED = "COMPLETED", "Hoàn tất"
        EXPIRED = "EXPIRED", "Hết hạn"
        LOCKED = "LOCKED", "Đã khóa"
        CANCELLED = "CANCELLED", "Đã hủy"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_requests")
    channel = models.CharField(max_length=10, choices=Channel.choices)
    destination = models.CharField(max_length=254)
    otp_hash = models.CharField(max_length=255)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    failed_attempt_count = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    last_sent_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    reset_token_hash = models.CharField(max_length=255, blank=True)
    reset_token_expires_at = models.DateTimeField(null=True, blank=True)
    reset_token_used_at = models.DateTimeField(null=True, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "password_reset_requests"
        ordering = ["-created_at"]

    @property
    def public_id(self):
        return f"pwd_reset_{self.id.hex}"


class PasswordResetAttempt(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    reset_request = models.ForeignKey(
        PasswordResetRequest,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="send_attempts",
    )
    identifier_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "password_reset_attempts"


class ActivityLog(models.Model):
    class Event(models.TextChoices):
        REQUESTED = "PASSWORD_RESET_REQUESTED", "Yêu cầu đặt lại mật khẩu"
        OTP_VERIFIED = "PASSWORD_RESET_OTP_VERIFIED", "Đã xác thực mã"
        COMPLETED = "PASSWORD_RESET_COMPLETED", "Hoàn tất đặt lại mật khẩu"

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=50, choices=Event.choices, db_index=True)
    success = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    device_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "activity_logs"
        ordering = ["-created_at", "-id"]
