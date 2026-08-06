"""Vietnamese labels and presentation helpers shared by web and API views."""

import json
import re


DISPLAY_LABELS = {
    # Vai trò và phạm vi vận hành.
    "founder": "Nhà sáng lập / Quản trị viên",
    "housekeeping": "Nhân viên buồng phòng",
    "housekeeping_lead": "Trưởng nhóm buồng phòng",
    "HOUSEKEEPER": "Nhân viên buồng phòng",
    "HOUSEKEEPING_LEAD": "Trưởng nhóm buồng phòng",
    "MANAGER": "Quản lý",
    "QC": "Kiểm tra chất lượng",
    "WAREHOUSE": "Kho",
    "TECHNICIAN": "Kỹ thuật",
    "VIEWER": "Chỉ xem",
    # Trạng thái, mức ưu tiên và loại công việc.
    "UNASSIGNED": "Chờ phân công",
    "ASSIGNED": "Đã phân công",
    "PENDING_ACCEPTANCE": "Chờ nhận việc",
    "ACCEPTED": "Đã nhận việc",
    "IN_PROGRESS": "Đang thực hiện",
    "PAUSED": "Tạm dừng",
    "WAITING_SUPPORT": "Chờ hỗ trợ",
    "COMPLETED": "Đã hoàn thành",
    "WAITING_QC": "Chờ kiểm tra chất lượng",
    "QC_REJECTED": "Kiểm tra không đạt",
    "QC_APPROVED": "Kiểm tra đạt",
    "CANCELLED": "Đã hủy",
    "BOOKED": "Đã đặt",
    "CHECKED_IN": "Đã nhận phòng",
    "CHECKED_OUT": "Đã trả phòng",
    "DRAFT": "Nháp",
    "PUBLISHED": "Đã phát hành",
    "RETIRED": "Ngừng sử dụng",
    "PENDING": "Chờ xử lý",
    "APPROVED": "Đạt",
    "REJECTED": "Không đạt",
    "RETURNED": "Đã trả lại",
    "REASSIGNED": "Đã điều chuyển",
    "ENDED": "Đã kết thúc",
    "OPEN": "Đang mở",
    "ACKNOWLEDGED": "Đã tiếp nhận",
    "FULFILLED": "Đã cấp",
    "RESOLVED": "Đã xử lý",
    "SENT_TO_QC": "Đã gửi kiểm tra chất lượng",
    "READY": "Sẵn sàng",
    "DIRTY": "Bẩn",
    "WAITING_CLEANING": "Chờ dọn",
    "CLEANING": "Đang dọn",
    "CLEANING_BLOCKED": "Dọn phòng bị chặn",
    "REWORK_REQUIRED": "Cần làm lại",
    "OUT_OF_SERVICE": "Ngừng phục vụ",
    "LOW": "Thấp",
    "NORMAL": "Bình thường",
    "HIGH": "Cao",
    "URGENT": "Khẩn cấp",
    "CHECKOUT_CLEANING": "Dọn phòng sau khi khách trả phòng",
    "STAYOVER_CLEANING": "Dọn phòng đang có khách",
    "CHECKIN_PREPARATION": "Chuẩn bị phòng đón khách",
    "DEEP_CLEANING": "Vệ sinh chuyên sâu",
    "QC_REWORK": "Dọn lại sau kiểm tra chất lượng",
    "PERIODIC_CLEANING": "Vệ sinh định kỳ",
    # Loại hạng mục, ảnh và trạng thái đồng bộ.
    "CHECKBOX": "Ô đánh dấu",
    "YES_NO": "Có hoặc không",
    "NUMBER": "Số lượng",
    "TEXT": "Văn bản",
    "PHOTO": "Chụp ảnh",
    "SINGLE_SELECT": "Chọn một",
    "MULTI_SELECT": "Chọn nhiều",
    "DEVICE_CHECK": "Kiểm tra thiết bị",
    "QR_SCAN": "Quét mã QR",
    "BEFORE": "Trước khi dọn",
    "AFTER": "Sau khi dọn",
    "ISSUE": "Sự cố",
    "SUPPLY": "Thiếu vật tư",
    "AREA": "Khu vực",
    "EVIDENCE": "Bằng chứng hoàn thành",
    "CAMERA": "Máy ảnh",
    "GALLERY": "Thư viện ảnh",
    "OFFLINE_CAMERA": "Máy ảnh ngoại tuyến",
    "RECEIVED": "Đã nhận",
    "SUCCEEDED": "Thành công",
    "FAILED": "Thất bại",
    "CONFLICT": "Xung đột",
    "DISCARDED": "Đã bỏ thay đổi trên thiết bị",
    "SYNCED": "Đã đồng bộ",
    "SYNCING": "Đang đồng bộ",
    # Lý do và phương thức.
    "WAITING_SUPPLIES": "Chờ vật tư",
    "DEVICE_BROKEN": "Thiết bị hỏng",
    "GUEST_IN_ROOM": "Khách đang trong phòng",
    "GUEST_REQUEST_LATER": "Khách yêu cầu quay lại sau",
    "WAITING_TECHNICIAN": "Chờ kỹ thuật",
    "WAITING_MANAGER": "Chờ quản lý",
    "HIGHER_PRIORITY_TASK": "Có công việc ưu tiên hơn",
    "BREAK": "Nghỉ giữa ca",
    "OTHER": "Lý do khác",
    "TASK_CREATED": "Tạo công việc",
    "MANUAL": "Tạo thủ công",
    "MANUAL_BACKOFFICE": "Thao tác thủ công trên trang quản trị",
    "QR_CODE": "Mã QR phòng",
    "GPS": "Vị trí GPS",
    "WIFI": "Mạng Wi-Fi",
    "MANAGER_OVERRIDE": "Quản lý xác nhận",
    "GUEST_CONSENT": "Khách đồng ý",
    # Thao tác, sự kiện và thông báo.
    "TASK_ACCEPTED": "Nhận công việc",
    "TASK_ASSIGNED": "Phân công công việc",
    "TASK_AVAILABLE": "Có công việc mới",
    "TASK_CANCELLED": "Hủy công việc",
    "TASK_COMPLETED": "Hoàn thành công việc",
    "TASK_NOTE_UPDATED": "Cập nhật ghi chú công việc",
    "TASK_PAUSED": "Tạm dừng công việc",
    "TASK_PRIORITY_CHANGED": "Đổi mức ưu tiên",
    "TASK_PROGRESS_UPDATED": "Cập nhật tiến độ",
    "TASK_QC_APPROVED": "Kiểm tra chất lượng đạt",
    "TASK_QC_REJECTED": "Kiểm tra chất lượng không đạt",
    "TASK_READY_FOR_QC": "Sẵn sàng kiểm tra chất lượng",
    "TASK_REASSIGNED": "Điều chuyển công việc",
    "TASK_REJECTED": "Từ chối công việc",
    "TASK_RESUMED": "Tiếp tục công việc",
    "TASK_RETURNED": "Trả lại công việc",
    "TASK_REWORK_STARTED": "Bắt đầu làm lại",
    "TASK_SENT_TO_QC": "Gửi kiểm tra chất lượng",
    "TASK_STARTED": "Bắt đầu công việc",
    "TASK_VIEWED": "Xem công việc",
    "CHECKLIST_FAILURE_ACCEPTED": "Chấp thuận hạng mục không đạt",
    "CHECKLIST_ITEM_UPDATED": "Cập nhật hạng mục kiểm tra",
    "PHOTO_ADDED": "Thêm ảnh",
    "MANAGER_NOTE_ADDED": "Quản lý thêm ghi chú",
    "SUPPLY_REQUEST_CREATED": "Tạo yêu cầu vật tư",
    "SUPPLY_REQUEST_STATUS_CHANGED": "Đổi trạng thái yêu cầu vật tư",
    "SUPPLY_REQUEST_UPDATED": "Cập nhật yêu cầu vật tư",
    "ISSUE_REPORTED": "Báo sự cố",
    "ISSUE_STATUS_CHANGED": "Đổi trạng thái sự cố",
    "ISSUE_UPDATED": "Cập nhật sự cố",
    "SLA_CHECKIN_RISK": "Nguy cơ trễ giờ nhận phòng",
    "SLA_CHECKIN_RISK_MARKED_URGENT": "Đánh dấu khẩn cấp do nguy cơ trễ giờ nhận phòng",
    "SLA_ESCALATION": "Cảnh báo quá hạn xử lý",
    "SLA_NEAR_DUE": "Sắp đến hạn xử lý",
    "SLA_OVERDUE": "Quá hạn xử lý",
    "ACCEPT": "Nhận việc",
    "START": "Bắt đầu",
    "PAUSE": "Tạm dừng",
    "RESUME": "Tiếp tục",
    "COMPLETE": "Hoàn thành",
    "RETURN": "Trả lại",
    "REJECT": "Từ chối",
    "REASSIGN": "Điều chuyển",
    "SEND_TO_QC": "Gửi kiểm tra chất lượng",
    "QC_APPROVE": "Duyệt đạt",
    "QC_REJECT": "Đánh giá không đạt",
    "START_REWORK": "Bắt đầu làm lại",
    "WAIT_SUPPORT": "Chờ hỗ trợ",
    "CREATE_SUPPLY_REQUEST": "Tạo yêu cầu vật tư",
    "REPORT_ISSUE": "Báo sự cố",
    "UPDATE_CHECKLIST_ITEM": "Cập nhật hạng mục kiểm tra",
    "UPDATE_TASK_NOTE": "Cập nhật ghi chú công việc",
    "RETRY_WITH_SERVER_VERSION": "Thử lại theo phiên bản trên máy chủ",
    "DISCARD_LOCAL": "Bỏ thay đổi trên thiết bị",
    "DEVICE_NOT_WORKING": "Thiết bị không hoạt động",
    "DAMAGE": "Hư hỏng",
    "SAFETY": "An toàn",
    "Deluxe": "Cao cấp",
    "DELUXE": "Cao cấp",
    "Suite": "Phòng hạng sang",
    "SUITE": "Phòng hạng sang",
    "CHECKLIST_REQUIRED_INCOMPLETE": "Còn hạng mục bắt buộc chưa hoàn tất",
    "FAILED_ITEM_UNRESOLVED": "Hạng mục không đạt chưa được xử lý",
    "REQUIRED_PHOTO_MISSING": "Thiếu ảnh bắt buộc",
    "BLOCKING_ISSUE_EXISTS": "Còn sự cố chặn phòng",
    "SUPPLY_REQUEST_PENDING": "Còn yêu cầu vật tư đang chờ",
    "PENDING_SYNC_EXISTS": "Còn dữ liệu chưa đồng bộ",
}


FIELD_LABELS = {
    "source": "Nguồn tạo",
    "assigneeId": "Mã người được giao",
    "from": "Từ",
    "to": "Sang",
    "reason": "Lý do",
    "taskId": "Mã công việc",
    "taskVersion": "Phiên bản công việc",
    "issueId": "Mã sự cố",
    "requestId": "Mã yêu cầu",
    "requestVersion": "Phiên bản yêu cầu",
    "issueVersion": "Phiên bản sự cố",
    "assignedToId": "Mã người xử lý",
    "fromAssigneeId": "Người làm trước",
    "toAssigneeId": "Người làm mới",
    "blocksRoomReady": "Chặn phòng sẵn sàng",
    "thresholdMinutes": "Ngưỡng cảnh báo (phút)",
    "maxOverdueMinutes": "Số phút quá hạn lớn nhất",
    "nextCheckinAt": "Giờ nhận phòng tiếp theo",
    "priority": "Mức ưu tiên",
    "status": "Trạng thái",
    "version": "Phiên bản",
    "operation": "Thao tác",
    "payload": "Nội dung thay đổi",
    "baseVersion": "Phiên bản dữ liệu gốc",
    "baseSnapshot": "Dữ liệu gốc",
    "localOperation": "Thay đổi trên thiết bị",
    "serverSnapshot": "Dữ liệu trên máy chủ",
    "roomStatus": "Trạng thái phòng",
    "progressPercent": "Tiến độ phần trăm",
    "updatedAt": "Cập nhật lúc",
    "itemId": "Mã hạng mục",
    "checklistItemId": "Mã hạng mục kiểm tra",
    "checklistItem": "Hạng mục kiểm tra",
    "itemVersion": "Phiên bản hạng mục",
    "value": "Giá trị",
    "note": "Ghi chú",
    "failureReason": "Lý do không đạt",
    "reasonCode": "Loại lý do",
    "completedAt": "Hoàn thành lúc",
}


def display_label(value):
    if value in (None, ""):
        return ""
    text = str(value)
    return DISPLAY_LABELS.get(text, text)


def _localized_json_value(value):
    if isinstance(value, dict):
        return {
            FIELD_LABELS.get(str(key), str(key)): _localized_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_localized_json_value(item) for item in value]
    if isinstance(value, str):
        return display_label(value)
    return value


def localized_json(value):
    return json.dumps(_localized_json_value(value), ensure_ascii=False, default=str)


_SYSTEM_TEXT_REPLACEMENTS = (
    ("Housekeeping", "buồng phòng"),
    ("Check-in", "nhận phòng"),
    ("Check-out", "trả phòng"),
    ("Booking", "đặt phòng"),
    ("Checklist", "danh sách kiểm tra"),
    ("Ticket", "phiếu sự cố"),
    ("Server", "máy chủ"),
    ("Task", "công việc"),
    ("SLA", "thời hạn xử lý"),
    ("QC", "kiểm tra chất lượng"),
)


def localized_system_text(value):
    """Việt hóa thông báo hệ thống cũ mà không sửa mã có dấu gạch nối."""
    text = str(value or "")
    for source, target in _SYSTEM_TEXT_REPLACEMENTS:
        text = re.sub(
            rf"(?<![-\w]){re.escape(source)}(?![-\w])",
            target,
            text,
            flags=re.IGNORECASE,
        )
    return text
