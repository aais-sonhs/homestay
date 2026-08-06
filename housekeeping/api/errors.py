import json
import logging
import uuid
from functools import wraps

from django.http import JsonResponse
from django.views.csrf import csrf_failure as django_csrf_failure

from common.idempotency import IdempotencyError
from housekeeping.services import HousekeepingError


logger = logging.getLogger(__name__)


class APIError(Exception):
    def __init__(self, code, message, *, status=400, details=None):
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}
        super().__init__(message)


def correlation_id(request):
    value = getattr(request, "correlation_id", "") or request.headers.get("X-Request-ID", "")
    value = str(value).strip()[:64] or str(uuid.uuid4())
    request.correlation_id = value
    return value


def parse_json(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise APIError("SYSTEM_ERROR", "Dữ liệu JSON không hợp lệ.") from None
    if not isinstance(payload, dict):
        raise APIError("SYSTEM_ERROR", "Dữ liệu JSON phải là một đối tượng.")
    return payload


def error_response(request, code, message, *, status=400, details=None):
    return JsonResponse(
        {
            "success": False,
            "code": code,
            "message": message,
            "details": details or {},
            "correlationId": correlation_id(request),
        },
        status=status,
    )


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/v1/housekeeping/"):
        return error_response(
            request,
            "CSRF_FAILED",
            "Mã bảo vệ biểu mẫu không hợp lệ hoặc bị thiếu.",
            status=403,
        )
    return django_csrf_failure(request, reason=reason)


def success_response(request, data, *, status=200, pagination=None, replayed=False):
    payload = {
        "success": True,
        "data": data,
        "correlationId": correlation_id(request),
    }
    if pagination is not None:
        payload["pagination"] = pagination
    response = JsonResponse(payload, status=status)
    if replayed:
        response["Idempotent-Replayed"] = "true"
    return response


def api_endpoint(*methods):
    allowed = {method.upper() for method in methods}

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            correlation_id(request)
            if request.method not in allowed:
                return error_response(
                    request,
                    "METHOD_NOT_ALLOWED",
                    "Phương thức HTTP không được hỗ trợ.",
                    status=405,
                    details={"allowedMethods": sorted(allowed)},
                )
            try:
                return view(request, *args, **kwargs)
            except (HousekeepingError, APIError) as error:
                return error_response(
                    request,
                    error.code,
                    error.message,
                    status=error.status,
                    details=error.details,
                )
            except IdempotencyError as error:
                status = 409 if error.code in {
                    "IDEMPOTENCY_KEY_REUSED",
                    "OFFLINE_SYNC_CONFLICT",
                    "MUTATION_IN_PROGRESS",
                } else 400
                details = {}
                if error.receipt:
                    details["receiptId"] = str(error.receipt.id)
                    details["receiptStatus"] = error.receipt.status
                    details["resultVersion"] = error.receipt.result_version
                return error_response(request, error.code, error.message, status=status, details=details)
            except Exception:
                logger.exception("Unhandled Housekeeping API error", extra={"correlation_id": correlation_id(request)})
                return error_response(
                    request,
                    "SYSTEM_ERROR",
                    "Hệ thống không thể xử lý yêu cầu lúc này.",
                    status=500,
                )

        return wrapped

    return decorator
