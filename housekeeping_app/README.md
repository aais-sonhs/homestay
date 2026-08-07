# Bliss Home — ứng dụng nội bộ

Một Flutter codebase dùng chung cho Chủ chi nhánh/Quản lý, Tạp vụ và QC. Sau đăng
nhập, app đọc role từ phiên bảo mật và tự mở đúng workspace; backend vẫn là nguồn
kiểm tra quyền cuối cùng. Web Django chỉ là backoffice/fallback online và không còn
lưu nghiệp vụ trong `localStorage`.

## Workspace theo vai trò

- **Chủ chi nhánh/Quản lý/Founder:** 5 tab Tổng quan, Công việc, Phòng, QC và
  Thông báo. Dashboard lấy SLA/hiệu suất thật; Trạng thái phòng là read-only, có
  blocker, dừng bán và rủi ro check-in theo đúng scope chi nhánh.
- **Tạp vụ:** danh sách và chi tiết công việc offline-first, QR/GPS/Wi-Fi/camera,
  checklist, ảnh, pause/resume, vật tư, sự cố và gửi QC.
- **QC:** mở thẳng ba nhóm Chờ kiểm tra, Làm lại và Hoàn thành; detail dùng
  capability từ backend để duyệt đạt hoặc trả lại đúng vòng kiểm tra.
- Các role Kho/Kỹ thuật/Sales/CSKH chưa có workspace mobile trong bản này; app
  không tự cấp nhầm giao diện hay quyền khi các tài khoản đó đăng nhập.

## Bảo mật và offline

- Access/refresh token chỉ nằm trong `flutter_secure_storage`; app không lưu password.
- Khóa SQLCipher 256-bit sinh bằng `Random.secure()` và chỉ lưu trong secure storage.
- Task, room, checklist, queue, conflict và photo BLOB đều nằm trong database SQLCipher.
- Mỗi mutation/media có client UUID + idempotency key, base version, dependency và state `pending/syncing/synced/failed/conflict/discarded`.
- Sync tự chạy khi connectivity thay đổi nhưng vẫn bắt lỗi từng HTTP request; connectivity không được xem là bằng chứng có Internet.
- Version conflict không tự rebase. Màn hình yêu cầu người dùng bỏ local hoặc chủ động retry trên server version hiện tại.
- Complete bị disable khi task còn pending/failed/conflict.
- Cache được bind với user UUID trong SQLCipher; đổi tài khoản không thể đọc cache của người trước. Logout bị chặn khi còn unresolved work và secure-delete cache khi hoàn tất.
- Hồ sơ phiên gồm ID, tên và role cũng nằm trong secure storage; app không suy đoán
  role từ giao diện hoặc dữ liệu cache.

## UI hiện trường

- 7 tab: Việc của tôi, Chờ nhận, Đang làm, Chờ hỗ trợ, Chờ QC, Làm lại, Hoàn thành.
- Search và filter theo ngày/chi nhánh/tầng/loại phòng/task/ưu tiên/overdue/check-in risk; mỗi view có cache riêng.
- Danh sách tự lấy progress/version mới mỗi 30 giây khi online; countdown vẫn cập nhật cục bộ.
- Task card có countdown, cảnh báo chữ + icon, tiến độ/checklist/ảnh và sync state.
- Detail có task/room/booking/SLA, 9 typed checklist controls, ảnh local/server, vật tư/sự cố, QC/rework và timeline.
- Conflict sheet bắt buộc xem base/local/server trước khi discard hoặc explicit retry.
- Completion summary dùng blocker từ backend; offline chỉ queue và backend vẫn là nguồn validation cuối.
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

- Android `minSdk` 24, `android:allowBackup="false"`, cleartext bị tắt ở release và ProGuard giữ SQLCipher.
- Release bật minify/resource shrinking, không dùng debug signing config.
- iOS có mô tả quyền camera/photo và Keychain entitlement cho secure storage.
- Production dùng `--dart-define=API_BASE_URL=https://homestay.aaistech.com` và
  chỉ cho phép HTTPS.

## Luồng sync

1. Tải task list/detail online và cache vào SQLCipher.
2. Khi offline, queue checklist/note/pause/supply/issue/photo; photo bytes không ghi ra public storage.
3. Dependency planner gửi prerequisite và mutation phụ thuộc cùng batch theo đúng thứ tự.
4. Backend `/sync/batch` trả receipt riêng cho từng mutation.
5. `CONFLICT` giữ base/local/server snapshot để người dùng resolve; `FAILED` có nút retry.
6. Sau khi không còn dữ liệu unresolved, app mới cho gửi complete.
