from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from common.api_auth import api_authenticated
from housekeeping.api.errors import APIError, api_endpoint, parse_json, success_response

from .identifiers import normalize_email, normalize_phone
from .models import AccessToken, RefreshToken, User


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
