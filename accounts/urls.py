from django.contrib.auth.views import LogoutView
from django.urls import path

from .views import (
    BlissHomeLoginView,
    api_forgot_password_request,
    api_forgot_password_resend_otp,
    api_forgot_password_reset,
    api_forgot_password_verify_otp,
    avatar_update,
    development_mailbox,
    documentation,
    forgot_password_done,
    forgot_password_otp,
    forgot_password_request,
    forgot_password_resend,
    forgot_password_reset,
    password_change,
)
from .token_api import login_token, logout_token, refresh_token, register_account


urlpatterns = [
    path("login/", BlissHomeLoginView.as_view(), name="public-login"),
    path("logout/", LogoutView.as_view(), name="public-logout"),
    path("accounts/login/", BlissHomeLoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/password/change/", password_change, name="password-change"),
    path("accounts/profile/avatar/", avatar_update, name="avatar-update"),
    path("documentation/", documentation, name="documentation"),
    path("forgot-password/", forgot_password_request, name="forgot-password"),
    path("forgot-password/otp/", forgot_password_otp, name="forgot-password-otp"),
    path("forgot-password/resend/", forgot_password_resend, name="forgot-password-resend"),
    path("forgot-password/reset/", forgot_password_reset, name="forgot-password-reset"),
    path("forgot-password/done/", forgot_password_done, name="forgot-password-done"),
    path("dev/mailbox/", development_mailbox, name="development-mailbox"),
    path("api/v1/auth/forgot-password/request", api_forgot_password_request, name="api-forgot-password-request"),
    path("api/v1/auth/forgot-password/verify-otp", api_forgot_password_verify_otp, name="api-forgot-password-verify-otp"),
    path("api/v1/auth/forgot-password/resend-otp", api_forgot_password_resend_otp, name="api-forgot-password-resend-otp"),
    path("api/v1/auth/forgot-password/reset", api_forgot_password_reset, name="api-forgot-password-reset"),
    path("api/v1/auth/forgot-password/request/", api_forgot_password_request),
    path("api/v1/auth/forgot-password/verify-otp/", api_forgot_password_verify_otp),
    path("api/v1/auth/forgot-password/resend-otp/", api_forgot_password_resend_otp),
    path("api/v1/auth/forgot-password/reset/", api_forgot_password_reset),
    path("api/v1/auth/login", login_token, name="api-token-login"),
    path("api/v1/auth/login/", login_token),
    path("api/v1/auth/register", register_account, name="api-account-register"),
    path("api/v1/auth/register/", register_account),
    path("api/v1/auth/refresh", refresh_token, name="api-token-refresh"),
    path("api/v1/auth/refresh/", refresh_token),
    path("api/v1/auth/logout", logout_token, name="api-token-logout"),
    path("api/v1/auth/logout/", logout_token),
]
