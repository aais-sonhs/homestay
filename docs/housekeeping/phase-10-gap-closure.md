# Phase 10 — Gap closure sau đối chiếu PLAN

Ngày kiểm chứng: 06/08/2026 (Asia/Ho_Chi_Minh).

## Phạm vi đã đóng

- Founder/Admin/Manager có thể tạo task qua API idempotent và backoffice; server kiểm tra scope, snapshot checklist đã phát hành, tạo assignment/history/SLA và notification.
- `HousekeepingTask.required_skills` được bổ sung bằng migration additive `0006`; task mở chỉ hiện cho nhân viên có đủ toàn bộ skill, accept/reassign đều kiểm tra lại ở backend.
- Detail API và web ghi activity `TASK_VIEWED`.
- Quản lý có thể cập nhật ghi chú task; assignee nhận notification. Flutter có Notification Center và đánh dấu đã đọc.
- `startup.sh` chạy evaluator SLA định kỳ với lifecycle gắn vào Uvicorn.
- Flutter có filter area/shift/status/assignee/QC rework; QR checklist và QR phòng dùng scanner camera, GPS lấy từ thiết bị, Wi-Fi lấy BSSID/SSID thực.
- Camera verification offline giữ dependency ảnh → START, đổi client media ID thành server photo ID trước sync. Receipt upload media lưu client ID để backend xác nhận dependency bền vững.
- QC có thể chụp media loại `QC` trong task detail; gallery bị khóa ở chế độ QC.
- Android/iOS đã khai báo quyền camera/location/network và entitlement đọc Wi-Fi phù hợp.

## Bằng chứng test

- Django SQLite: 106 test, 104 pass và 2 PostgreSQL-only skip.
- PostgreSQL concurrency: 2/2 pass.
- Flutter analyze: 0 issue.
- Flutter unit/widget: 10/10 pass.
- `makemigrations --check --dry-run`, Django system check và `startup.sh` syntax pass.
- Migration `housekeeping.0006_housekeepingtask_required_skills` đã áp dụng thành công lên PostgreSQL `homestay`.

## Giới hạn vận hành còn lại

- Không restart/stop tiến trình do người dùng quản lý ở cổng `8020`; cần người dùng restart để worker nạp source mới rồi mới smoke test runtime.
- Android build và physical-device E2E vẫn đang hoãn theo chỉ dẫn hiện có trong PLAN. Scanner/GPS/Wi-Fi/camera đã được khóa bằng analyze/unit/source contract, chưa thay thế được kiểm chứng thiết bị thật.
- Production vẫn cần domain/TLS và settings bảo mật; cấu hình hiện tại là local development.
