from functools import wraps
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from accounts.models import AccessToken

from housekeeping.api.errors import error_response


class BearerAuthenticationMiddleware:
    """Authenticate Bearer requests before CSRF; session requests remain CSRF protected."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.auth_token = None
        request.bearer_auth_error = ""
        authorization = request.headers.get("Authorization", "").strip()
        if authorization:
            # An explicit Authorization header must never fall back to cookie
            # authentication. The API decorator will return a JSON 401 when it
            # is malformed, so CSRF is irrelevant for this request.
            request._dont_enforce_csrf_checks = True
            parts = authorization.split()
            if len(parts) != 2 or parts[0].lower() != "bearer":
                request.bearer_auth_error = "INVALID_AUTHORIZATION"
            else:
                # Bearer requests do not use cookie authentication, so CSRF is
                # not applicable. Invalid tokens are still rejected by the API.
                key = parts[1]
                token = None
                if len(key) <= 64:
                    token = (
                        AccessToken.objects.select_related("user")
                        .filter(
                            key=key,
                            revoked_at__isnull=True,
                            created_at__gt=timezone.now()
                            - timedelta(seconds=settings.API_ACCESS_TOKEN_TTL_SECONDS),
                        )
                        .first()
                    )
                user = token.user if token else None
                if (
                    user is None
                    or not user.is_active
                    or user.is_deleted
                    or user.is_permanently_disabled
                    or user.disabled_by_admin
                ):
                    request.bearer_auth_error = "INVALID_TOKEN"
                else:
                    request.user = user
                    request.auth_token = token
                    AccessToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
        return self.get_response(request)


def api_authenticated(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if getattr(request, "bearer_auth_error", ""):
            return error_response(
                request,
                "TASK_ACCESS_DENIED",
                "Bearer token không hợp lệ hoặc đã bị thu hồi.",
                status=401,
            )
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return error_response(
                request,
                "TASK_ACCESS_DENIED",
                "Vui lòng đăng nhập.",
                status=401,
            )
        if not user.is_active or user.is_deleted:
            return error_response(request, "TASK_ACCESS_DENIED", "Tài khoản không hoạt động.", status=403)
        return view(request, *args, **kwargs)

    return wrapped
