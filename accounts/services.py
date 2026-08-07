import ipaddress
import re
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.core.signing import salted_hmac
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .errors import PasswordResetError
from .identifiers import mask_destination, normalize_identifier
from .models import (
    AccessToken,
    ActivityLog,
    PasswordHistory,
    PasswordResetAttempt,
    PasswordResetRequest,
    RefreshToken,
    User,
)
from .notifications import send_otp, send_security_notification


GENERIC_REQUEST_MESSAGE = "Nếu thông tin bạn nhập tồn tại trong hệ thống, mã xác thực sẽ được gửi đến bạn."


@transaction.atomic
def change_authenticated_password(*, user, current_password, new_password, confirm_password):
    """Change an authenticated user's password and revoke every other credential."""
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    if locked_user.is_deleted or locked_user.is_permanently_disabled:
        raise PasswordResetError(
            "ACCOUNT_DISABLED",
            "Tài khoản không thể đổi mật khẩu. Vui lòng liên hệ quản trị viên.",
        )
    if not locked_user.check_password(str(current_password or "")):
        raise PasswordResetError(
            "CURRENT_PASSWORD_INVALID",
            "Mật khẩu hiện tại không chính xác.",
        )
    if new_password != confirm_password:
        raise PasswordResetError(
            "PASSWORD_NOT_MATCH",
            "Xác nhận mật khẩu không khớp.",
        )
    policy_errors = password_policy_errors(str(new_password or ""), locked_user)
    if policy_errors:
        raise PasswordResetError(
            "PASSWORD_POLICY_FAILED",
            policy_errors[0],
            extra={"errors": policy_errors},
        )
    recent_hashes = [locked_user.password]
    recent_hashes.extend(
        locked_user.password_history.values_list("password_hash", flat=True)[:3]
    )
    if any(
        check_password(new_password, encoded)
        for encoded in recent_hashes
        if encoded
    ):
        raise PasswordResetError(
            "PASSWORD_REUSED",
            "Mật khẩu mới không được trùng mật khẩu hiện tại hoặc 3 mật khẩu gần nhất.",
        )

    now = timezone.now()
    if locked_user.password:
        PasswordHistory.objects.create(
            user=locked_user,
            password_hash=locked_user.password,
        )
    locked_user.set_password(new_password)
    locked_user.password_changed_at = now
    locked_user.save(update_fields=["password", "password_changed_at"])
    AccessToken.objects.filter(
        user=locked_user,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    RefreshToken.objects.filter(
        user=locked_user,
        revoked_at__isnull=True,
    ).update(revoked_at=now)
    _revoke_sessions(locked_user)
    return locked_user


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",", 1)[0].strip()
    candidate = forwarded or request.META.get("REMOTE_ADDR", "").strip()
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def request_context(request):
    return {
        "ip": client_ip(request),
        "device_id": request.headers.get("X-Device-ID", "")[:255],
        "user_agent": request.headers.get("User-Agent", "")[:2000],
    }


def _setting(name):
    return int(getattr(settings, name))


def _request_uuid(public_id):
    prefix = "pwd_reset_"
    if not isinstance(public_id, str) or not public_id.startswith(prefix):
        raise PasswordResetError("OTP_INVALID", "Yêu cầu đặt lại mật khẩu không hợp lệ.")
    try:
        return uuid.UUID(hex=public_id[len(prefix) :])
    except (ValueError, AttributeError):
        raise PasswordResetError("OTP_INVALID", "Yêu cầu đặt lại mật khẩu không hợp lệ.") from None


def _get_reset_request(public_id, *, lock=False):
    queryset = PasswordResetRequest.objects.select_related("user")
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=_request_uuid(public_id))
    except PasswordResetRequest.DoesNotExist:
        raise PasswordResetError("OTP_INVALID", "Yêu cầu đặt lại mật khẩu không hợp lệ.") from None


def _find_eligible_user(channel, identifier):
    query = Q(email__iexact=identifier) if channel == "email" else Q(normalized_phone=identifier)
    return (
        User.objects.filter(query, is_deleted=False)
        .filter(is_permanently_disabled=False, disabled_by_admin=False)
        .order_by("id")
        .first()
    )


def _destination_for(reset_request):
    if reset_request.channel == PasswordResetRequest.Channel.EMAIL:
        return reset_request.user.email
    return reset_request.user.normalized_phone


def _identifier_fingerprint(identifier):
    return salted_hmac("password-reset-identifier", identifier).hexdigest()


def _rate_limit(user, identifier_fingerprint, ip, now):
    attempts = PasswordResetAttempt.objects.all()
    if ip:
        ip_count = attempts.filter(
            ip_address=ip,
            created_at__gte=now - timedelta(hours=24),
        ).count()
        if ip_count >= _setting("PASSWORD_RESET_IP_LIMIT_24_HOURS"):
            raise PasswordResetError(
                "RATE_LIMIT_EXCEEDED",
                "Bạn đã yêu cầu mã xác thực quá nhiều lần. Vui lòng thử lại sau.",
                status=429,
            )
    account_attempts = (
        attempts.filter(user=user)
        if user is not None
        else attempts.filter(identifier_fingerprint=identifier_fingerprint)
    )
    recent_count = account_attempts.filter(
        created_at__gte=now - timedelta(minutes=15),
    ).count()
    daily_count = account_attempts.filter(
        created_at__gte=now - timedelta(hours=24),
    ).count()
    if (
        recent_count >= _setting("PASSWORD_RESET_ACCOUNT_LIMIT_15_MINUTES")
        or daily_count >= _setting("PASSWORD_RESET_ACCOUNT_LIMIT_24_HOURS")
    ):
        raise PasswordResetError(
            "RATE_LIMIT_EXCEEDED",
            "Bạn đã yêu cầu mã xác thực quá nhiều lần. Vui lòng thử lại sau.",
            status=429,
        )


def _log(*, user, event, success, context, metadata=None):
    # Metadata is deliberately limited to non-secret status information.
    ActivityLog.objects.create(
        user=user,
        event_type=event,
        success=success,
        ip_address=context.get("ip"),
        device_id=context.get("device_id", ""),
        metadata=metadata or {},
    )


def request_password_reset(*, identifier, channel, context):
    try:
        normalized_channel, normalized_identifier = normalize_identifier(identifier, channel)
    except ValidationError as error:
        raise PasswordResetError("INVALID_IDENTIFIER", error.messages[0]) from None

    now = timezone.now()
    user = _find_eligible_user(normalized_channel, normalized_identifier)
    fingerprint = _identifier_fingerprint(normalized_identifier)
    _rate_limit(user, fingerprint, context.get("ip"), now)

    if user is None:
        # Spend password-hasher work on the non-existing-account path as well,
        # reducing the usefulness of response timing for account enumeration.
        make_password(f"{secrets.randbelow(1_000_000):06d}")
        PasswordResetAttempt.objects.create(
            identifier_fingerprint=fingerprint,
            ip_address=context.get("ip"),
        )
        _log(
            user=None,
            event=ActivityLog.Event.REQUESTED,
            success=True,
            context=context,
            metadata={"delivered": False},
        )
        return {
            "request_id": f"pwd_reset_{uuid.uuid4().hex}",
            "delivered": False,
        }

    otp = f"{secrets.randbelow(1_000_000):06d}"
    with transaction.atomic():
        PasswordResetRequest.objects.filter(
            user=user,
            status__in=[PasswordResetRequest.Status.PENDING, PasswordResetRequest.Status.VERIFIED],
        ).update(status=PasswordResetRequest.Status.CANCELLED, updated_at=now)
        reset_request = PasswordResetRequest.objects.create(
            user=user,
            channel=normalized_channel,
            destination=mask_destination(normalized_identifier, normalized_channel),
            otp_hash=make_password(otp),
            expires_at=now + timedelta(seconds=_setting("PASSWORD_RESET_OTP_TTL_SECONDS")),
            last_sent_at=now,
            request_ip=context.get("ip"),
            device_id=context.get("device_id", ""),
            user_agent=context.get("user_agent", ""),
        )
        PasswordResetAttempt.objects.create(
            user=user,
            reset_request=reset_request,
            identifier_fingerprint=fingerprint,
            ip_address=context.get("ip"),
        )
    try:
        send_otp(channel=normalized_channel, destination=normalized_identifier, otp=otp)
    except Exception:
        PasswordResetRequest.objects.filter(pk=reset_request.pk).update(
            status=PasswordResetRequest.Status.CANCELLED,
        )
        _log(
            user=user,
            event=ActivityLog.Event.REQUESTED,
            success=False,
            context=context,
            metadata={"channel": normalized_channel, "result": "delivery_failed"},
        )
        # The public response remains identical to an unknown account, avoiding
        # account enumeration when the delivery provider is unavailable.
        return {"request_id": reset_request.public_id, "delivered": False}
    _log(
        user=user,
        event=ActivityLog.Event.REQUESTED,
        success=True,
        context=context,
        metadata={"channel": normalized_channel, "delivered": True},
    )
    return {"request_id": reset_request.public_id, "delivered": True}


def verify_otp(*, request_id, otp, context):
    value = str(otp or "").strip()
    if not re.fullmatch(r"\d{6}", value):
        raise PasswordResetError("OTP_INVALID", "Mã xác thực phải gồm đúng 6 chữ số.")
    pending_error = None
    token = None
    with transaction.atomic():
        reset_request = _get_reset_request(request_id, lock=True)
        now = timezone.now()

        if reset_request.status == PasswordResetRequest.Status.LOCKED:
            pending_error = PasswordResetError(
                "OTP_ATTEMPTS_EXCEEDED",
                "Mã xác thực đã bị khóa do nhập sai quá nhiều lần. Vui lòng yêu cầu mã mới.",
                status=423,
            )
        elif reset_request.status in {
            PasswordResetRequest.Status.VERIFIED,
            PasswordResetRequest.Status.COMPLETED,
            PasswordResetRequest.Status.CANCELLED,
        }:
            pending_error = PasswordResetError(
                "OTP_ALREADY_USED",
                "Mã xác thực đã được sử dụng hoặc không còn hiệu lực.",
            )
        elif reset_request.expires_at <= now or reset_request.status == PasswordResetRequest.Status.EXPIRED:
            reset_request.status = PasswordResetRequest.Status.EXPIRED
            reset_request.save(update_fields=["status", "updated_at"])
            pending_error = PasswordResetError(
                "OTP_EXPIRED",
                "Mã xác thực đã hết hạn. Vui lòng yêu cầu mã mới.",
            )
        elif not check_password(value, reset_request.otp_hash):
            reset_request.failed_attempt_count += 1
            remaining = max(
                0,
                _setting("PASSWORD_RESET_MAX_OTP_ATTEMPTS") - reset_request.failed_attempt_count,
            )
            if remaining == 0:
                reset_request.status = PasswordResetRequest.Status.LOCKED
            reset_request.save(update_fields=["failed_attempt_count", "status", "updated_at"])
            _log(
                user=reset_request.user,
                event=ActivityLog.Event.OTP_VERIFIED,
                success=False,
                context=context,
                metadata={"result": "invalid", "remaining_attempts": remaining},
            )
            if remaining == 0:
                pending_error = PasswordResetError(
                    "OTP_ATTEMPTS_EXCEEDED",
                    "Mã xác thực đã bị khóa do nhập sai quá nhiều lần. Vui lòng yêu cầu mã mới.",
                    status=423,
                )
            else:
                pending_error = PasswordResetError(
                    "OTP_INVALID",
                    f"Mã xác thực không chính xác. Bạn còn {remaining} lần thử.",
                    extra={"remainingAttempts": remaining},
                )
        else:
            secret = secrets.token_urlsafe(32)
            reset_request.status = PasswordResetRequest.Status.VERIFIED
            reset_request.verified_at = now
            reset_request.reset_token_hash = make_password(secret)
            reset_request.reset_token_expires_at = now + timedelta(
                seconds=_setting("PASSWORD_RESET_TOKEN_TTL_SECONDS")
            )
            reset_request.save(
                update_fields=[
                    "status",
                    "verified_at",
                    "reset_token_hash",
                    "reset_token_expires_at",
                    "updated_at",
                ]
            )
            _log(
                user=reset_request.user,
                event=ActivityLog.Event.OTP_VERIFIED,
                success=True,
                context=context,
            )
            token = f"{reset_request.public_id}.{secret}"
    if pending_error:
        raise pending_error
    return token


def resend_otp(*, request_id, context):
    now = timezone.now()
    with transaction.atomic():
        reset_request = _get_reset_request(request_id, lock=True)
        if reset_request.status in {
            PasswordResetRequest.Status.VERIFIED,
            PasswordResetRequest.Status.COMPLETED,
            PasswordResetRequest.Status.CANCELLED,
        }:
            raise PasswordResetError("OTP_ALREADY_USED", "Yêu cầu này không thể gửi lại mã xác thực.")
        wait_seconds = _setting("PASSWORD_RESET_RESEND_AFTER_SECONDS") - int(
            (now - reset_request.last_sent_at).total_seconds()
        )
        if wait_seconds > 0:
            raise PasswordResetError(
                "OTP_RESEND_TOO_SOON",
                f"Vui lòng chờ {wait_seconds} giây trước khi gửi lại mã.",
                status=429,
                extra={"resendAfterSeconds": wait_seconds},
            )
        _rate_limit(reset_request.user, "", context.get("ip"), now)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        reset_request.otp_hash = make_password(otp)
        reset_request.status = PasswordResetRequest.Status.PENDING
        reset_request.failed_attempt_count = 0
        reset_request.resend_count += 1
        reset_request.expires_at = now + timedelta(seconds=_setting("PASSWORD_RESET_OTP_TTL_SECONDS"))
        reset_request.last_sent_at = now
        reset_request.verified_at = None
        reset_request.reset_token_hash = ""
        reset_request.reset_token_expires_at = None
        reset_request.save()
        PasswordResetAttempt.objects.create(
            user=reset_request.user,
            reset_request=reset_request,
            identifier_fingerprint=_identifier_fingerprint(_destination_for(reset_request)),
            ip_address=context.get("ip"),
        )
    try:
        send_otp(
            channel=reset_request.channel,
            destination=_destination_for(reset_request),
            otp=otp,
        )
    except Exception:
        _log(
            user=reset_request.user,
            event=ActivityLog.Event.REQUESTED,
            success=False,
            context=context,
            metadata={"channel": reset_request.channel, "resend": True, "result": "delivery_failed"},
        )
        raise PasswordResetError(
            "SYSTEM_ERROR",
            "Không thể gửi mã xác thực lúc này. Vui lòng thử lại sau.",
            status=503,
        ) from None
    _log(
        user=reset_request.user,
        event=ActivityLog.Event.REQUESTED,
        success=True,
        context=context,
        metadata={"channel": reset_request.channel, "resend": True},
    )
    return reset_request


def password_policy_errors(password, user):
    errors = []
    if len(password) < 8:
        errors.append("Mật khẩu phải có tối thiểu 8 ký tự.")
    if len(password) > 128:
        errors.append("Mật khẩu không được vượt quá 128 ký tự.")
    if not any(character.isupper() for character in password):
        errors.append("Mật khẩu phải có ít nhất một chữ hoa.")
    if not any(character.islower() for character in password):
        errors.append("Mật khẩu phải có ít nhất một chữ thường.")
    if not any(character.isdigit() for character in password):
        errors.append("Mật khẩu phải có ít nhất một chữ số.")
    if not any(not character.isalnum() and not character.isspace() for character in password):
        errors.append("Mật khẩu phải có ít nhất một ký tự đặc biệt.")
    if re.search(r"\s", password):
        errors.append("Mật khẩu không được chứa khoảng trắng.")

    lowered = password.lower()
    forbidden = [user.username.lower()]
    if user.email:
        forbidden.extend([user.email.lower(), user.email.split("@", 1)[0].lower()])
    if user.normalized_phone:
        forbidden.append(re.sub(r"\D", "", user.normalized_phone))
    compact_password = re.sub(r"\D", "", password)
    for value in forbidden:
        if len(value) >= 3 and (value in lowered or (value.isdigit() and value in compact_password)):
            errors.append("Mật khẩu không được chứa tên đăng nhập, thư điện tử hoặc số điện thoại.")
            break
    try:
        password_validation.validate_password(password, user=user)
    except ValidationError as error:
        errors.extend(error.messages)
    return list(dict.fromkeys(errors))


def _revoke_sessions(user):
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        try:
            if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
                session.delete()
        except Exception:
            continue


def reset_password(*, reset_token, new_password, confirm_password, context):
    token = str(reset_token or "")
    if "." not in token:
        raise PasswordResetError("RESET_TOKEN_INVALID", "Mã đặt lại mật khẩu không hợp lệ.")
    request_id, secret = token.split(".", 1)
    try:
        preliminary_request = _get_reset_request(request_id)
    except PasswordResetError:
        raise PasswordResetError("RESET_TOKEN_INVALID", "Mã đặt lại mật khẩu không hợp lệ.") from None
    preliminary_now = timezone.now()
    if (
        preliminary_request.status == PasswordResetRequest.Status.VERIFIED
        and preliminary_request.reset_token_expires_at
        and preliminary_request.reset_token_expires_at <= preliminary_now
    ):
        PasswordResetRequest.objects.filter(
            pk=preliminary_request.pk,
            status=PasswordResetRequest.Status.VERIFIED,
        ).update(status=PasswordResetRequest.Status.EXPIRED, updated_at=preliminary_now)
        raise PasswordResetError("RESET_TOKEN_EXPIRED", "Mã đặt lại mật khẩu đã hết hạn.")
    return _reset_password_atomic(
        request_id=request_id,
        secret=secret,
        new_password=new_password,
        confirm_password=confirm_password,
        context=context,
    )


@transaction.atomic
def _reset_password_atomic(*, request_id, secret, new_password, confirm_password, context):
    reset_request = _get_reset_request(request_id, lock=True)
    now = timezone.now()
    if reset_request.status == PasswordResetRequest.Status.COMPLETED or reset_request.reset_token_used_at:
        raise PasswordResetError("RESET_TOKEN_INVALID", "Mã đặt lại mật khẩu đã được sử dụng.")
    if reset_request.status != PasswordResetRequest.Status.VERIFIED:
        raise PasswordResetError("RESET_TOKEN_INVALID", "Mã đặt lại mật khẩu không hợp lệ.")
    if not reset_request.reset_token_expires_at or reset_request.reset_token_expires_at <= now:
        reset_request.status = PasswordResetRequest.Status.EXPIRED
        reset_request.save(update_fields=["status", "updated_at"])
        raise PasswordResetError("RESET_TOKEN_EXPIRED", "Mã đặt lại mật khẩu đã hết hạn.")
    if not secret or not check_password(secret, reset_request.reset_token_hash):
        raise PasswordResetError("RESET_TOKEN_INVALID", "Mã đặt lại mật khẩu không hợp lệ.")
    if new_password != confirm_password:
        raise PasswordResetError("PASSWORD_NOT_MATCH", "Xác nhận mật khẩu không khớp.")

    user = reset_request.user
    if user.is_deleted or user.is_permanently_disabled:
        raise PasswordResetError(
            "ACCOUNT_DISABLED",
            "Không thể xử lý yêu cầu. Vui lòng liên hệ quản trị viên.",
        )
    policy_errors = password_policy_errors(str(new_password or ""), user)
    if policy_errors:
        raise PasswordResetError(
            "PASSWORD_POLICY_FAILED",
            policy_errors[0],
            extra={"errors": policy_errors},
        )

    recent_hashes = [user.password]
    recent_hashes.extend(
        user.password_history.values_list("password_hash", flat=True)[:3]
    )
    if any(check_password(new_password, encoded) for encoded in recent_hashes if encoded):
        raise PasswordResetError("PASSWORD_REUSED", "Mật khẩu mới không được trùng mật khẩu hiện tại hoặc 3 mật khẩu gần nhất.")

    if user.password:
        PasswordHistory.objects.create(user=user, password_hash=user.password)
    user.set_password(new_password)
    user.password_changed_at = now
    update_fields = ["password", "password_changed_at"]
    if user.locked_due_to_failed_logins and not user.disabled_by_admin:
        user.locked_due_to_failed_logins = False
        user.is_active = True
        update_fields.extend(["locked_due_to_failed_logins", "is_active"])
    user.save(update_fields=update_fields)

    AccessToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    RefreshToken.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=now)
    _revoke_sessions(user)
    reset_request.status = PasswordResetRequest.Status.COMPLETED
    reset_request.completed_at = now
    reset_request.reset_token_used_at = now
    reset_request.reset_token_hash = ""
    reset_request.save(
        update_fields=[
            "status",
            "completed_at",
            "reset_token_used_at",
            "reset_token_hash",
            "updated_at",
        ]
    )
    PasswordResetRequest.objects.filter(user=user).exclude(pk=reset_request.pk).filter(
        status__in=[PasswordResetRequest.Status.PENDING, PasswordResetRequest.Status.VERIFIED]
    ).update(status=PasswordResetRequest.Status.CANCELLED, updated_at=now)
    _log(
        user=user,
        event=ActivityLog.Event.COMPLETED,
        success=True,
        context=context,
    )
    transaction.on_commit(
        lambda: _send_security_notice_safely(reset_request, now)
    )
    return user


def _send_security_notice_safely(reset_request, changed_at):
    try:
        send_security_notification(
            channel=reset_request.channel,
            destination=_destination_for(reset_request),
            changed_at=timezone.localtime(changed_at),
        )
    except Exception:
        # Password reset remains successful if the secondary alert provider is unavailable.
        pass
