import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email


PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email(value):
    normalized = str(value or "").strip().lower()
    validate_email(normalized)
    return normalized


def normalize_phone(value):
    raw = str(value or "").strip()
    has_plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):
        normalized = "+84" + digits[1:]
    elif digits.startswith("84"):
        normalized = "+" + digits
    elif has_plus:
        normalized = "+" + digits
    else:
        raise ValidationError("Số điện thoại phải có mã quốc gia hoặc bắt đầu bằng 0.")
    if not PHONE_RE.fullmatch(normalized):
        raise ValidationError("Số điện thoại không đúng định dạng.")
    return normalized


def normalize_identifier(value, channel=None):
    raw = str(value or "").strip()
    selected_channel = str(channel or "").strip().lower()
    if selected_channel not in {"", "email", "sms"}:
        raise ValidationError("Kênh nhận mã xác thực không hợp lệ.")
    if selected_channel == "email" or (not selected_channel and "@" in raw):
        return "email", normalize_email(raw)
    if selected_channel == "sms" or not selected_channel:
        return "sms", normalize_phone(raw)
    raise ValidationError("Thư điện tử hoặc số điện thoại không đúng định dạng.")


def mask_destination(value, channel):
    if channel == "email":
        local, domain = value.split("@", 1)
        visible = local[:2] if len(local) > 2 else local[:1]
        return f"{visible}{'*' * max(3, len(local) - len(visible))}@{domain}"
    return f"{value[:3]}{'*' * max(4, len(value) - 7)}{value[-4:]}"
