from importlib import import_module

from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ImproperlyConfigured


def dummy_sms_backend(*, destination, message):
    """Phương án an toàn tại máy cục bộ: nhận tin nhưng không in mã xác thực."""
    if not settings.PASSWORD_RESET_ALLOW_LOCAL_DELIVERY:
        raise ImproperlyConfigured("Phải cấu hình dịch vụ gửi tin nhắn đặt lại mật khẩu trên môi trường vận hành.")
    return 1


def _load_backend(path):
    module_name, function_name = path.rsplit(".", 1)
    return getattr(import_module(module_name), function_name)


def send_otp(*, channel, destination, otp):
    message = (
        f"Mã xác thực đặt lại mật khẩu Bliss Home của bạn là {otp}. "
        "Mã có hiệu lực trong 5 phút. Không chia sẻ mã này cho người khác."
    )
    if channel == "email":
        if not settings.PASSWORD_RESET_ALLOW_LOCAL_DELIVERY and settings.EMAIL_BACKEND.endswith(
            ("locmem.EmailBackend", "filebased.EmailBackend")
        ):
            raise ImproperlyConfigured("Phải cấu hình dịch vụ gửi thư trên môi trường vận hành.")
        return send_mail(
            "Mã xác thực đặt lại mật khẩu Bliss Home",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [destination],
            fail_silently=False,
        )
    backend = _load_backend(settings.PASSWORD_RESET_SMS_BACKEND)
    return backend(destination=destination, message=message)


def send_security_notification(*, channel, destination, changed_at):
    local_time = changed_at.strftime("%H:%M ngày %d/%m/%Y")
    message = (
        f"Mật khẩu tài khoản Bliss Home của bạn vừa được thay đổi vào lúc {local_time}. "
        "Nếu bạn không thực hiện thao tác này, vui lòng liên hệ quản trị viên ngay."
    )
    if channel == "email":
        return send_mail(
            "Mật khẩu Bliss Home vừa được thay đổi",
            message,
            settings.DEFAULT_FROM_EMAIL,
            [destination],
            fail_silently=True,
        )
    backend = _load_backend(settings.PASSWORD_RESET_SMS_BACKEND)
    return backend(destination=destination, message=message)
