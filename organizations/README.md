# Organizations

Ranh giới ứng dụng dành cho chi nhánh, khu vực, phòng, ca làm việc, nhóm và
phân quyền thành viên.

Các model hiện vẫn do migration của `housekeeping` quản lý để bảo toàn dữ liệu
và tên bảng đang chạy. Code mới có thể import qua `organizations.models`; không
tạo migration đổi `app_label` nếu chưa có kế hoạch chuyển trạng thái model và
kiểm thử dữ liệu PostgreSQL riêng.

