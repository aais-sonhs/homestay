from housekeeping.models import BookingSpecialRequest, HousekeepingTask


MAX_SPECIAL_REQUEST_ITEMS = 20


class SpecialRequestValidationError(ValueError):
    pass


def _choice_values(choices):
    return {value for value, _label in choices}


def _choice_label(choices, value):
    return dict(choices).get(value, value)


def normalize_special_request_items(raw_items=None, *, legacy_text=""):
    """Return a stable, validated representation accepted by booking services."""
    if raw_items is None:
        legacy_text = str(legacy_text or "").strip()
        raw_items = (
            [
                {
                    "request_type": BookingSpecialRequest.RequestType.OTHER,
                    "applies_to": BookingSpecialRequest.AppliesTo.ALL,
                    "priority": BookingSpecialRequest.Priority.NORMAL,
                    "description": legacy_text,
                }
            ]
            if legacy_text
            else []
        )
    if not isinstance(raw_items, (list, tuple)):
        raise SpecialRequestValidationError("Danh sách yêu cầu đặc biệt không hợp lệ.")
    if len(raw_items) > MAX_SPECIAL_REQUEST_ITEMS:
        raise SpecialRequestValidationError(
            f"Mỗi booking chỉ được có tối đa {MAX_SPECIAL_REQUEST_ITEMS} yêu cầu đặc biệt."
        )

    valid_types = _choice_values(BookingSpecialRequest.RequestType.choices)
    valid_phases = _choice_values(BookingSpecialRequest.AppliesTo.choices)
    valid_priorities = _choice_values(BookingSpecialRequest.Priority.choices)
    normalized = []
    for position, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            raise SpecialRequestValidationError("Từng yêu cầu đặc biệt phải là dữ liệu có cấu trúc.")
        if raw.get("DELETE") or raw.get("delete"):
            continue
        description = str(raw.get("description") or "").strip()
        if not description:
            continue
        if len(description) > 500:
            raise SpecialRequestValidationError("Nội dung yêu cầu đặc biệt không được quá 500 ký tự.")
        request_type = str(
            raw.get("request_type")
            or raw.get("requestType")
            or BookingSpecialRequest.RequestType.OTHER
        )
        applies_to = str(
            raw.get("applies_to")
            or raw.get("appliesTo")
            or BookingSpecialRequest.AppliesTo.CHECKIN
        )
        priority = str(
            raw.get("priority") or BookingSpecialRequest.Priority.NORMAL
        )
        if request_type not in valid_types:
            raise SpecialRequestValidationError("Loại yêu cầu đặc biệt không hợp lệ.")
        if applies_to not in valid_phases:
            raise SpecialRequestValidationError("Thời điểm áp dụng yêu cầu đặc biệt không hợp lệ.")
        if priority not in valid_priorities:
            raise SpecialRequestValidationError("Mức ưu tiên yêu cầu đặc biệt không hợp lệ.")

        quantity = raw.get("quantity")
        if quantity in (None, ""):
            quantity = None
        else:
            try:
                quantity = int(quantity)
            except (TypeError, ValueError):
                raise SpecialRequestValidationError("Số lượng yêu cầu đặc biệt không hợp lệ.") from None
            if not 1 <= quantity <= 99:
                raise SpecialRequestValidationError("Số lượng yêu cầu đặc biệt phải từ 1 đến 99.")
        normalized.append(
            {
                "request_type": request_type,
                "applies_to": applies_to,
                "priority": priority,
                "description": description,
                "quantity": quantity,
                "sort_order": position,
            }
        )
    return normalized


def canonical_special_request_items(items):
    return [
        {
            "request_type": item["request_type"],
            "applies_to": item["applies_to"],
            "priority": item["priority"],
            "description": item["description"],
            "quantity": item.get("quantity"),
            "sort_order": position,
        }
        for position, item in enumerate(items)
    ]


def serialize_special_request_item(item):
    if isinstance(item, BookingSpecialRequest):
        request_id = str(item.id)
        request_type = item.request_type
        applies_to = item.applies_to
        priority = item.priority
        description = item.description
        quantity = item.quantity
    else:
        request_id = str(item.get("id") or item.get("sourceRequestId") or "") or None
        request_type = item.get("request_type") or item.get("requestType")
        applies_to = item.get("applies_to") or item.get("appliesTo")
        priority = item.get("priority")
        description = item.get("description")
        quantity = item.get("quantity")
    return {
        "sourceRequestId": request_id,
        "requestType": request_type,
        "requestTypeLabel": _choice_label(BookingSpecialRequest.RequestType.choices, request_type),
        "appliesTo": applies_to,
        "appliesToLabel": _choice_label(BookingSpecialRequest.AppliesTo.choices, applies_to),
        "priority": priority,
        "priorityLabel": _choice_label(BookingSpecialRequest.Priority.choices, priority),
        "description": description,
        "quantity": quantity,
    }


def booking_special_request_items(booking):
    return list(booking.special_request_items.all().order_by("sort_order", "created_at", "id"))


def serialize_booking_special_requests(booking):
    return [serialize_special_request_item(item) for item in booking_special_request_items(booking)]


def special_request_summary(items):
    parts = []
    for item in items:
        description = item.description if isinstance(item, BookingSpecialRequest) else item["description"]
        quantity = item.quantity if isinstance(item, BookingSpecialRequest) else item.get("quantity")
        parts.append(f"{quantity} × {description}" if quantity else description)
    return "; ".join(parts)


def replace_booking_special_requests(booking, items, actor):
    booking.special_request_items.all().delete()
    BookingSpecialRequest.objects.bulk_create(
        [
            BookingSpecialRequest(
                booking=booking,
                branch=booking.branch,
                request_type=item["request_type"],
                applies_to=item["applies_to"],
                priority=item["priority"],
                description=item["description"],
                quantity=item.get("quantity"),
                sort_order=position,
                created_by=actor,
            )
            for position, item in enumerate(items)
        ]
    )
    return booking_special_request_items(booking)


def task_special_request_items(booking, task_type):
    phase_map = {
        HousekeepingTask.TaskType.CHECKIN_PREPARATION: {
            BookingSpecialRequest.AppliesTo.CHECKIN,
            BookingSpecialRequest.AppliesTo.STAY,
            BookingSpecialRequest.AppliesTo.ALL,
        },
        HousekeepingTask.TaskType.CHECKOUT_CLEANING: {
            BookingSpecialRequest.AppliesTo.CHECKOUT,
            BookingSpecialRequest.AppliesTo.ALL,
        },
    }
    phases = phase_map.get(task_type, {BookingSpecialRequest.AppliesTo.ALL})
    return [
        serialize_special_request_item(item)
        for item in booking_special_request_items(booking)
        if item.applies_to in phases
    ]
