import hashlib
import math
import re
from decimal import Decimal, InvalidOperation

from .models import TaskChecklistItem


class ChecklistValueError(Exception):
    pass


def _option_values(options):
    values = []
    for option in options or []:
        if isinstance(option, dict):
            values.append(option.get("value"))
        else:
            values.append(option)
    return values


def _validate_number(value, rules):
    if isinstance(value, bool):
        raise ChecklistValueError("Giá trị số không được là giá trị đúng/sai.")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ChecklistValueError("Giá trị phải là một số hợp lệ.") from None
    if not number.is_finite():
        raise ChecklistValueError("Giá trị số phải hữu hạn.")
    if rules.get("integer") and number != number.to_integral_value():
        raise ChecklistValueError("Giá trị phải là số nguyên.")
    for key, compare, message in (
        ("min", lambda left, right: left >= right, "Giá trị nhỏ hơn mức tối thiểu."),
        ("max", lambda left, right: left <= right, "Giá trị lớn hơn mức tối đa."),
    ):
        if rules.get(key) is not None:
            try:
                boundary = Decimal(str(rules[key]))
            except InvalidOperation:
                continue
            if not compare(number, boundary):
                raise ChecklistValueError(message)
    if number == number.to_integral_value():
        return int(number)
    as_float = float(number)
    if not math.isfinite(as_float):
        raise ChecklistValueError("Giá trị số vượt phạm vi hỗ trợ.")
    return as_float


def _validate_text(value, rules):
    if not isinstance(value, str):
        raise ChecklistValueError("Giá trị phải là văn bản.")
    normalized = value.strip()
    minimum = int(rules.get("minLength", 1 if rules.get("required", True) else 0))
    maximum = int(rules.get("maxLength", 2000))
    if len(normalized) < minimum:
        raise ChecklistValueError("Nội dung ngắn hơn độ dài tối thiểu.")
    if len(normalized) > maximum:
        raise ChecklistValueError("Nội dung vượt độ dài tối đa.")
    pattern = rules.get("pattern")
    if pattern:
        try:
            matched = re.fullmatch(str(pattern), normalized)
        except re.error:
            matched = None
        if not matched:
            raise ChecklistValueError("Nội dung không đúng định dạng yêu cầu.")
    return normalized


def validate_checklist_value(item, status, value):
    if status == TaskChecklistItem.Status.PENDING:
        return None

    rules = item.validation_snapshot or {}
    item_type = item.item_type
    if status == TaskChecklistItem.Status.FAILED and value is None:
        return None

    if item_type == TaskChecklistItem.ItemType.CHECKBOX:
        if not isinstance(value, bool):
            raise ChecklistValueError("Ô đánh dấu phải có giá trị đúng hoặc sai.")
        if status == TaskChecklistItem.Status.COMPLETED and value is not True:
            raise ChecklistValueError("Ô đánh dấu hoàn thành phải được xác nhận là đúng.")
        return value

    if item_type == TaskChecklistItem.ItemType.YES_NO:
        if not isinstance(value, bool):
            raise ChecklistValueError("Mục Có/Không phải có giá trị đúng hoặc sai.")
        expected = rules.get("expectedValue")
        if status == TaskChecklistItem.Status.COMPLETED and expected is not None and value is not expected:
            raise ChecklistValueError("Giá trị Có/Không không đạt điều kiện mong đợi.")
        return value

    if item_type == TaskChecklistItem.ItemType.NUMBER:
        return _validate_number(value, rules)

    if item_type == TaskChecklistItem.ItemType.TEXT:
        return _validate_text(value, rules)

    if item_type == TaskChecklistItem.ItemType.PHOTO:
        required_count = max(1, int(rules.get("requiredPhotoCount", 1)))
        if status == TaskChecklistItem.Status.COMPLETED and item.photos.count() < required_count:
            raise ChecklistValueError(f"Cần tải đủ {required_count} ảnh trước khi hoàn tất mục này.")
        return value

    if item_type == TaskChecklistItem.ItemType.SINGLE_SELECT:
        allowed = _option_values(item.options_snapshot)
        if value not in allowed:
            raise ChecklistValueError("Giá trị không thuộc danh sách được phép.")
        return value

    if item_type == TaskChecklistItem.ItemType.MULTI_SELECT:
        if not isinstance(value, list):
            raise ChecklistValueError("Mục chọn nhiều phải là một danh sách.")
        allowed = _option_values(item.options_snapshot)
        if any(option not in allowed for option in value):
            raise ChecklistValueError("Danh sách có giá trị không được phép.")
        if len(value) != len(set(map(str, value))):
            raise ChecklistValueError("Danh sách không được chứa giá trị trùng.")
        minimum = int(rules.get("minSelections", 1))
        maximum = int(rules.get("maxSelections", len(allowed)))
        if not minimum <= len(value) <= maximum:
            raise ChecklistValueError("Số lựa chọn không nằm trong phạm vi cho phép.")
        return value

    if item_type == TaskChecklistItem.ItemType.DEVICE_CHECK:
        if not isinstance(value, bool):
            raise ChecklistValueError("Kiểm tra thiết bị phải có giá trị đúng hoặc sai.")
        if status == TaskChecklistItem.Status.COMPLETED and value is not True:
            raise ChecklistValueError("Thiết bị không hoạt động phải được đánh dấu Không đạt.")
        return value

    if item_type == TaskChecklistItem.ItemType.QR_SCAN:
        scanned = _validate_text(value, {"minLength": 1, "maxLength": 512})
        expected_hash = str(rules.get("expectedHash") or "")
        if expected_hash and hashlib.sha256(scanned.encode("utf-8")).hexdigest() != expected_hash:
            raise ChecklistValueError("Mã QR/mã vạch không đúng giá trị yêu cầu.")
        allowed = rules.get("allowedValues")
        if allowed and scanned not in allowed:
            raise ChecklistValueError("Mã QR/mã vạch không thuộc danh sách cho phép.")
        return scanned

    raise ChecklistValueError("Loại hạng mục kiểm tra chưa được hỗ trợ.")
