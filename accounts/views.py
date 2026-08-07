import json
from email import policy
from email.parser import BytesParser
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .errors import PasswordResetError
from .forms import (
    AuthenticatedPasswordChangeForm,
    AvatarUpdateForm,
    ForgotPasswordRequestForm,
    ResetPasswordForm,
    VerifyOTPForm,
)
from .services import (
    GENERIC_REQUEST_MESSAGE,
    change_authenticated_password,
    request_context,
    request_password_reset,
    resend_otp,
    reset_password,
    verify_otp,
)


class BlissHomeLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True


@login_required
def dashboard(request):
    return redirect("housekeeping:task-list")


@login_required
def documentation(request):
    return render(request, "documentation.html")


@login_required
@require_http_methods(["GET", "POST"])
def password_change(request):
    form = AuthenticatedPasswordChangeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            changed_user = change_authenticated_password(
                user=request.user,
                current_password=form.cleaned_data["current_password"],
                new_password=form.cleaned_data["new_password"],
                confirm_password=form.cleaned_data["confirm_password"],
            )
        except PasswordResetError as error:
            field = {
                "CURRENT_PASSWORD_INVALID": "current_password",
                "PASSWORD_NOT_MATCH": "confirm_password",
                "PASSWORD_POLICY_FAILED": "new_password",
                "PASSWORD_REUSED": "new_password",
            }.get(error.code)
            form.add_error(field, error.message)
        else:
            update_session_auth_hash(request, changed_user)
            messages.success(request, "Mật khẩu đã được thay đổi thành công.")
            return redirect("housekeeping:task-list")
    return render(request, "registration/password_change_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def avatar_update(request):
    form = AvatarUpdateForm(
        request.POST or None,
        request.FILES or None,
        instance=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Ảnh đại diện đã được cập nhật.")
        return redirect("avatar-update")
    return render(request, "accounts/avatar_form.html", {"form": form})


def _payload(request):
    try:
        value = json.loads(request.body.decode("utf-8") or "{}")
        return value if isinstance(value, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _error_response(error):
    payload = {
        "success": False,
        "code": error.code,
        "message": error.message,
    }
    payload.update(error.extra)
    return JsonResponse(payload, status=error.status)


@csrf_exempt
@require_POST
def api_forgot_password_request(request):
    payload = _payload(request)
    if payload is None:
        return _error_response(PasswordResetError("INVALID_IDENTIFIER", "Dữ liệu JSON không hợp lệ."))
    try:
        result = request_password_reset(
            identifier=payload.get("identifier"),
            channel=payload.get("channel"),
            context=request_context(request),
        )
    except PasswordResetError as error:
        return _error_response(error)
    return JsonResponse(
        {
            "success": True,
            "message": GENERIC_REQUEST_MESSAGE,
            "requestId": result["request_id"],
            "resendAfterSeconds": settings.PASSWORD_RESET_RESEND_AFTER_SECONDS,
            "expiresInSeconds": settings.PASSWORD_RESET_OTP_TTL_SECONDS,
        }
    )


@csrf_exempt
@require_POST
def api_forgot_password_verify_otp(request):
    payload = _payload(request)
    if payload is None:
        return _error_response(PasswordResetError("OTP_INVALID", "Dữ liệu JSON không hợp lệ."))
    try:
        token = verify_otp(
            request_id=payload.get("requestId"),
            otp=payload.get("otp"),
            context=request_context(request),
        )
    except PasswordResetError as error:
        return _error_response(error)
    return JsonResponse(
        {
            "success": True,
            "resetToken": token,
            "expiresInSeconds": settings.PASSWORD_RESET_TOKEN_TTL_SECONDS,
        }
    )


@csrf_exempt
@require_POST
def api_forgot_password_resend_otp(request):
    payload = _payload(request)
    if payload is None:
        return _error_response(PasswordResetError("OTP_INVALID", "Dữ liệu JSON không hợp lệ."))
    try:
        resend_otp(
            request_id=payload.get("requestId"),
            context=request_context(request),
        )
    except PasswordResetError as error:
        return _error_response(error)
    return JsonResponse(
        {
            "success": True,
            "message": "Mã xác thực mới đã được gửi.",
            "resendAfterSeconds": settings.PASSWORD_RESET_RESEND_AFTER_SECONDS,
            "expiresInSeconds": settings.PASSWORD_RESET_OTP_TTL_SECONDS,
        }
    )


@csrf_exempt
@require_POST
def api_forgot_password_reset(request):
    payload = _payload(request)
    if payload is None:
        return _error_response(PasswordResetError("RESET_TOKEN_INVALID", "Dữ liệu JSON không hợp lệ."))
    try:
        reset_password(
            reset_token=payload.get("resetToken"),
            new_password=payload.get("newPassword", ""),
            confirm_password=payload.get("confirmPassword", ""),
            context=request_context(request),
        )
    except PasswordResetError as error:
        if error.code == "OTP_INVALID":
            error = PasswordResetError(
                "RESET_TOKEN_INVALID",
                "Mã đặt lại mật khẩu không hợp lệ.",
            )
        return _error_response(error)
    return JsonResponse(
        {
            "success": True,
            "message": "Mật khẩu đã được thay đổi thành công.",
        }
    )


def forgot_password_request(request):
    if request.method == "POST":
        form = ForgotPasswordRequestForm(request.POST)
        if form.is_valid():
            try:
                result = request_password_reset(
                    identifier=form.cleaned_data["identifier"],
                    channel=form.cleaned_data["channel"],
                    context=request_context(request),
                )
            except PasswordResetError as error:
                form.add_error(None, error.message)
            else:
                request.session["password_reset_request_id"] = result["request_id"]
                return redirect("forgot-password-otp")
    else:
        form = ForgotPasswordRequestForm()
    return render(request, "registration/forgot_password_request.html", {"form": form})


def forgot_password_otp(request):
    request_id = request.session.get("password_reset_request_id")
    if not request_id:
        return redirect("forgot-password")
    if request.method == "POST":
        form = VerifyOTPForm(request.POST)
        if form.is_valid():
            try:
                token = verify_otp(
                    request_id=request_id,
                    otp=form.cleaned_data["otp"],
                    context=request_context(request),
                )
            except PasswordResetError as error:
                form.add_error(None, error.message)
            else:
                request.session["password_reset_token"] = token
                return redirect("forgot-password-reset")
    else:
        form = VerifyOTPForm()
    notice = request.session.pop("password_reset_notice", "")
    return render(
        request,
        "registration/forgot_password_otp.html",
        {
            "form": form,
            "request_id": request_id,
            "notice": notice,
            "dev_mailbox_enabled": (
                settings.DEBUG and settings.PASSWORD_RESET_ENABLE_DEV_MAILBOX
            ),
        },
    )


@require_POST
def forgot_password_resend(request):
    request_id = request.session.get("password_reset_request_id")
    if not request_id:
        return redirect("forgot-password")
    try:
        resend_otp(request_id=request_id, context=request_context(request))
    except PasswordResetError as error:
        request.session["password_reset_notice"] = error.message
    else:
        request.session["password_reset_notice"] = "Mã xác thực mới đã được gửi."
    return redirect("forgot-password-otp")


def forgot_password_reset(request):
    token = request.session.get("password_reset_token")
    if not token:
        return redirect("forgot-password")
    if request.method == "POST":
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            try:
                reset_password(
                    reset_token=token,
                    new_password=form.cleaned_data["new_password"],
                    confirm_password=form.cleaned_data["confirm_password"],
                    context=request_context(request),
                )
            except PasswordResetError as error:
                form.add_error(None, error.message)
            else:
                # Flush the current browser session too; otherwise saving the
                # workflow session could recreate an authenticated session that
                # the reset service has just revoked.
                logout(request)
                return redirect("forgot-password-done")
    else:
        form = ResetPasswordForm()
    return render(request, "registration/forgot_password_reset.html", {"form": form})


def forgot_password_done(request):
    return render(request, "registration/forgot_password_done.html")


def development_mailbox(request):
    if not settings.DEBUG or not settings.PASSWORD_RESET_ENABLE_DEV_MAILBOX:
        raise Http404

    mailbox_path = Path(settings.EMAIL_FILE_PATH)
    messages = []
    if mailbox_path.exists():
        for message_path in sorted(
            (path for path in mailbox_path.iterdir() if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:20]:
            try:
                with message_path.open("rb") as message_file:
                    email_message = BytesParser(policy=policy.default).parse(message_file)
                body_part = email_message.get_body(preferencelist=("plain",))
                body = body_part.get_content() if body_part else email_message.get_payload()
                messages.append(
                    {
                        "subject": email_message.get("Subject", ""),
                        "to": email_message.get("To", ""),
                        "date": email_message.get("Date", ""),
                        "body": body,
                    }
                )
            except (OSError, ValueError):
                continue
    return render(request, "development_mailbox.html", {"email_messages": messages})
