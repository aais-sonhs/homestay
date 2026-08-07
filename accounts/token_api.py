import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from common.api_auth import api_authenticated
from housekeeping.api.errors import APIError, api_endpoint, parse_json, success_response

from .identifiers import normalize_email, normalize_phone
from .models import AccessToken, RefreshToken, User
from .services import password_policy_errors


def _active_user(identifier):
    value = str(identifier or "").strip()
    if not value:
        return None
    lookup = Q(username__iexact=value)
    try:
        normalized_email = normalize_email(value)
    except ValidationError:
        normalized_email = ""
    if normalized_email:
        lookup |= Q(email=normalized_email)
    try:
        normalized_phone = normalize_phone(value)
    except ValidationError:
        normalized_phone = ""
    if normalized_phone:
        lookup |= Q(normalized_phone=normalized_phone)
    return User.objects.filter(lookup).order_by("id").first()


def _user_allowed(user):
    return bool(
        user
        and user.is_active
        and not user.is_deleted
        and not user.is_permanently_disabled
        and not user.disabled_by_admin
        and not user.locked_due_to_failed_logins
    )


def _issue_pair(user, label):
    access = AccessToken.objects.create(
        user=user,
        label=str(label or "Ứng dụng hiện trường")[:100],
    )
    refresh = RefreshToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(seconds=settings.API_REFRESH_TOKEN_TTL_SECONDS),
    )
    return access, refresh


def _token_payload(access, refresh):
    return {
        "tokenType": "Bearer",
        "accessToken": access.key,
        "expiresInSeconds": settings.API_ACCESS_TOKEN_TTL_SECONDS,
        "refreshToken": refresh.key,
        "refreshExpiresInSeconds": settings.API_REFRESH_TOKEN_TTL_SECONDS,
        "user": {
            "id": str(access.user_id),
            "username": access.user.username,
            "name": access.user.get_full_name() or access.user.username,
            "role": access.user.role,
        },
    }


def _registration_username():
    while True:
        candidate = f"bh_{secrets.token_hex(8)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


@csrf_exempt
@api_endpoint("POST")
def register_account(request):
    payload = parse_json(request)
    full_name = str(payload.get("fullName") or "").strip()
    password = str(payload.get("password") or "")
    confirm_password = str(payload.get("confirmPassword") or "")

    if len(full_name) < 2 or len(full_name) > 150:
        raise APIError(
            "FULL_NAME_INVALID",
            "Họ và tên phải có từ 2 đến 150 ký tự.",
        )
    try:
        email = normalize_email(payload.get("email"))
    except ValidationError:
        raise APIError(
            "EMAIL_INVALID",
            "Thư điện tử không đúng định dạng.",
        ) from None
    try:
        phone = normalize_phone(payload.get("phoneNumber"))
    except ValidationError:
        raise APIError(
            "PHONE_INVALID",
            "Số điện thoại không đúng định dạng.",
        ) from None
    if password != confirm_password:
        raise APIError(
            "PASSWORD_NOT_MATCH",
            "Xác nhận mật khẩu không khớp.",
        )

    user = User(
        username=_registration_username(),
        first_name=full_name,
        email=email,
        phone_number=phone,
        role=User.Role.HOUSEKEEPING,
        is_active=True,
        is_staff=False,
        is_superuser=False,
        password_changed_at=timezone.now(),
    )
    errors = password_policy_errors(password, user)
    if errors:
        raise APIError(
            "PASSWORD_POLICY_FAILED",
            errors[0],
            details={"errors": errors},
        )

    try:
        with transaction.atomic():
            if User.objects.filter(email__iexact=email).exists():
                raise APIError(
                    "EMAIL_ALREADY_REGISTERED",
                    "Thư điện tử này đã được sử dụng.",
                    status=409,
                )
            if User.objects.filter(normalized_phone=phone).exists():
                raise APIError(
                    "PHONE_ALREADY_REGISTERED",
                    "Số điện thoại này đã được sử dụng.",
                    status=409,
                )
            user.set_password(password)
            user.save()
    except IntegrityError:
        raise APIError(
            "ACCOUNT_ALREADY_REGISTERED",
            "Thư điện tử hoặc số điện thoại đã được sử dụng.",
            status=409,
        ) from None

    return success_response(
        request,
        {
            "accountCreated": True,
            "identifier": email,
            "role": user.role,
            "requiresBranchAssignment": True,
            "message": (
                "Tài khoản đã được tạo. Bạn có thể đăng nhập ngay; "
                "quản trị viên sẽ gán chi nhánh và quyền làm việc."
            ),
        },
        status=201,
    )


@csrf_exempt
@api_endpoint("POST")
def login_token(request):
    payload = parse_json(request)
    user = _active_user(payload.get("identifier"))
    authenticated = None
    if user:
        authenticated = authenticate(request, username=user.username, password=str(payload.get("password") or ""))
    if not _user_allowed(authenticated):
        raise APIError("AUTHENTICATION_FAILED", "Thông tin đăng nhập không hợp lệ.", status=401)
    access, refresh = _issue_pair(authenticated, payload.get("deviceName"))
    return success_response(request, _token_payload(access, refresh), status=201)


@csrf_exempt
@api_endpoint("POST")
@transaction.atomic
def refresh_token(request):
    payload = parse_json(request)
    key = str(payload.get("refreshToken") or "")
    token = (
        RefreshToken.objects.select_for_update()
        .select_related("user")
        .filter(key=key, revoked_at__isnull=True, expires_at__gt=timezone.now())
        .first()
    )
    if token is None or not _user_allowed(token.user):
        raise APIError(
            "REFRESH_TOKEN_INVALID",
            "Mã làm mới phiên đăng nhập không hợp lệ hoặc đã hết hạn.",
            status=401,
        )
    token.revoke()
    access, replacement = _issue_pair(token.user, payload.get("deviceName"))
    return success_response(request, _token_payload(access, replacement), status=201)


@api_endpoint("POST")
@api_authenticated
def logout_token(request):
    payload = parse_json(request)
    if request.auth_token:
        request.auth_token.revoke()
    refresh_key = str(payload.get("refreshToken") or "")
    if refresh_key:
        RefreshToken.objects.filter(
            user=request.user,
            key=refresh_key,
            revoked_at__isnull=True,
        ).update(revoked_at=timezone.now())
    if request.session.session_key:
        logout(request)
    return success_response(request, {"loggedOut": True})
