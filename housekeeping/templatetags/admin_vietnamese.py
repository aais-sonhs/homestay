from django import template


register = template.Library()


MODEL_LABELS = {
    "AccessToken": "Mã truy cập",
    "ActivityLog": "Nhật ký hoạt động",
    "PasswordHistory": "Lịch sử mật khẩu",
    "PasswordResetRequest": "Yêu cầu đặt lại mật khẩu",
    "RefreshToken": "Mã làm mới phiên đăng nhập",
    "User": "Người dùng",
    "Area": "Khu vực",
    "Booking": "Đặt phòng",
    "BranchHousekeepingPolicy": "Chính sách buồng phòng chi nhánh",
    "BranchMembership": "Thành viên chi nhánh",
    "Branch": "Chi nhánh",
    "ChecklistItemDefinition": "Định nghĩa hạng mục kiểm tra",
    "ChecklistTemplate": "Mẫu danh sách kiểm tra",
    "ChecklistVersion": "Phiên bản danh sách kiểm tra",
    "HousekeepingActivityLog": "Nhật ký hoạt động buồng phòng",
    "HousekeepingTask": "Công việc buồng phòng",
    "HousekeepingTeam": "Nhóm buồng phòng",
    "IssueTicket": "Phiếu sự cố",
    "NotificationRecipient": "Người nhận thông báo",
    "Notification": "Thông báo",
    "OfflineMutationReceipt": "Bản ghi đồng bộ ngoại tuyến",
    "OutboxEvent": "Sự kiện chờ gửi",
    "QCFailedItem": "Hạng mục kiểm tra không đạt",
    "QCTask": "Công việc kiểm tra chất lượng",
    "ReworkRound": "Vòng làm lại",
    "Room": "Phòng",
    "SLAEscalationEvent": "Sự kiện cảnh báo quá hạn",
    "SLAPolicy": "Chính sách thời hạn xử lý",
    "ShiftAssignment": "Phân công ca",
    "Shift": "Ca làm việc",
    "Skill": "Kỹ năng",
    "SupplyLocation": "Điểm cấp vật tư",
    "SupplyRequest": "Yêu cầu vật tư",
    "TaskAssignment": "Phân công công việc",
    "TaskChecklistItem": "Hạng mục kiểm tra công việc",
    "TaskHandover": "Bàn giao công việc",
    "TaskPause": "Lượt tạm dừng công việc",
    "TaskPhoto": "Ảnh công việc",
    "TaskRoomVerification": "Xác minh phòng của công việc",
    "TaskSLAState": "Trạng thái thời hạn công việc",
    "TaskStatusHistory": "Lịch sử trạng thái công việc",
}


@register.filter
def vi_admin_model(object_name):
    return MODEL_LABELS.get(str(object_name), str(object_name))
