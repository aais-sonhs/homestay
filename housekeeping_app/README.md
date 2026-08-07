# Bliss Home — ứng dụng nội bộ

Một Flutter codebase dùng chung cho Chủ chi nhánh/Quản lý, Tạp vụ và QC. Sau đăng
nhập, app đọc role từ phiên bảo mật và tự mở đúng workspace; backend vẫn là nguồn
kiểm tra quyền cuối cùng. Web Django chỉ là backoffice/fallback online và không còn
lưu nghiệp vụ trong `localStorage`.

## Workspace theo vai trò

- **Chủ chi nhánh/Quản lý/Founder:** 5 tab Tổng quan, Công việc, Phòng, QC và
  Thông báo. Dashboard lấy SLA/hiệu suất thật; Trạng thái phòng là read-only, có
  blocker, dừng bán và rủi ro check-in theo đúng scope chi nhánh.
- **Tạp vụ:** danh sách và chi tiết công việc gọi API trực tiếp, QR/GPS/Wi-Fi/camera,
  checklist, ảnh, pause/resume, vật tư, sự cố và gửi QC.
- **QC:** mở thẳng ba nhóm Chờ kiểm tra, Làm lại và Hoàn thành; detail dùng
  capability từ backend để duyệt đạt hoặc trả lại đúng vòng kiểm tra.
- Các role Kho/Kỹ thuật/Sales/CSKH chưa có workspace mobile trong bản này; app
  không tự cấp nhầm giao diện hay quyền khi các tài khoản đó đăng nhập.

## Bảo mật và kết nối API

- Access/refresh token chỉ nằm trong `flutter_secure_storage`; app không lưu password.
- App không dùng SQLite/SQLCipher và không lưu task, checklist hay ảnh trong database cục bộ.
- Login, dashboard, phòng, thông báo, task list/detail và mọi mutation/media đều gọi
  trực tiếp `https://homestay.aaistech.com` qua HTTPS.
- Mỗi mutation/media vẫn có UUID, idempotency key và base version để backend chống
  gửi trùng và phát hiện version conflict.
- App cần có Internet để đọc và cập nhật nghiệp vụ; backend là nguồn dữ liệu và kiểm
  tra quyền duy nhất.
- Hồ sơ phiên gồm ID, tên và role nằm trong secure storage; app không suy đoán role
  từ giao diện.

## UI hiện trường

- 7 tab: Việc của tôi, Chờ nhận, Đang làm, Chờ hỗ trợ, Chờ QC, Làm lại, Hoàn thành.
- Search và các nhóm công việc được gửi thành query lên API.
- Danh sách tự lấy progress/version mới mỗi 30 giây.
- Task card có countdown, cảnh báo chữ + icon, tiến độ/checklist và ảnh.
- Detail có task/room/booking/SLA, typed checklist controls, ảnh server, vật tư/sự cố,
  QC/rework và timeline.
- Completion summary và toàn bộ blocker được lấy trực tiếp từ backend.
- API readiness mobile không trả tên/SĐT khách và luôn scope qua membership/ownership
  ở server.

## Chạy và kiểm thử

Platform project Android/iOS đã được generate. Dùng Flutter 3.38+/Dart 3.10+:

```bash
cd housekeeping_app
flutter pub get
flutter analyze
flutter test
flutter build apk --debug --dart-define=API_BASE_URL=https://homestay.aaistech.com
```

Các cấu hình bảo mật platform đã áp dụng:

- Android `minSdk` 24, `android:allowBackup="false"` và cleartext bị tắt ở release.
- Release dùng keystore riêng, tắt minify/resource shrinking để bảo toàn plugin native.
- iOS có mô tả quyền camera/photo và Keychain entitlement cho secure storage.
- Production dùng `--dart-define=API_BASE_URL=https://homestay.aaistech.com` và
  chỉ cho phép HTTPS.

## Luồng API

1. App mở thẳng màn hình login và gọi `/api/v1/auth/login`.
2. Sau login, workspace theo role tải dữ liệu trực tiếp từ API.
3. Checklist/note/pause/supply/issue dùng `/api/v1/housekeeping/sync/batch` ngay
   trong lúc thao tác, không ghi queue cục bộ.
4. Ảnh được upload multipart trực tiếp tới endpoint media.
5. Sau mỗi cập nhật thành công, app tải lại detail từ backend.
