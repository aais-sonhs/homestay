import uuid

from django.utils import timezone

from common.api_auth import api_authenticated
from housekeeping.api.errors import APIError, api_endpoint, success_response

from .selectors import build_readiness_board


def _iso_datetime(value):
    return timezone.localtime(value).isoformat() if value else None


def _readiness_row_data(row):
    room = row["room"]
    next_booking = row["nextBooking"]
    return {
        "room": {
            "id": str(room.id),
            "code": room.code,
            "name": room.name,
            "floor": room.floor,
            "area": room.area,
            "roomType": room.room_type,
            "status": room.status,
            "statusLabel": room.get_status_display(),
        },
        "branch": {
            "id": str(room.branch_id),
            "code": room.branch.code,
            "name": room.branch.name,
        },
        "state": row["state"],
        "stateLabel": row["stateLabel"],
        "readyForGuest": row["readyForGuest"],
        "salesStatus": row["salesStatus"],
        "salesStatusLabel": row["salesStatusLabel"],
        "checkinRisk": row["checkinRisk"],
        "expectedReadyAt": _iso_datetime(row["expectedReadyAt"]),
        "blockers": [
            {
                "code": blocker["code"],
                "label": blocker["label"],
                "level": blocker["level"],
            }
            for blocker in row["blockers"]
        ],
        "activeTaskCount": len(row["activeTasks"]),
        "blockingIssueCount": len(row["blockingIssues"]),
        "activeStopSells": [
            {
                "id": str(stop_sell.id),
                "status": stop_sell.status,
                "statusLabel": stop_sell.get_status_display(),
                "reason": stop_sell.reason,
                "plannedEndAt": _iso_datetime(stop_sell.planned_end_at),
            }
            for stop_sell in row["activeStopSells"]
        ],
        "nextBooking": (
            {
                "id": str(next_booking.id),
                "code": next_booking.code,
                "status": next_booking.status,
                "checkinAt": _iso_datetime(next_booking.checkin_at),
                "checkoutAt": _iso_datetime(next_booking.checkout_at),
            }
            if next_booking
            else None
        ),
    }


@api_endpoint("GET")
@api_authenticated
def room_readiness(request):
    branch_id = str(request.GET.get("branchId") or "").strip()
    if branch_id:
        try:
            branch_id = str(uuid.UUID(branch_id))
        except ValueError:
            raise APIError(
                "SYSTEM_ERROR",
                "Chi nhánh lọc trạng thái phòng không hợp lệ.",
            ) from None
    state = str(request.GET.get("state") or "").strip().upper()
    if state and state not in {"READY", "OCCUPIED", "NOT_READY", "BLOCKED"}:
        raise APIError(
            "SYSTEM_ERROR",
            "Trạng thái phòng lọc không hợp lệ.",
        )
    board = build_readiness_board(
        request.user,
        branch_id=branch_id or None,
        query=request.GET.get("q", ""),
        state=state,
    )
    return success_response(
        request,
        {
            "summary": board["summary"],
            "items": [_readiness_row_data(row) for row in board["rows"]],
        },
    )
