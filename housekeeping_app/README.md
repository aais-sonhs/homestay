# Bliss Home Housekeeping field app

Flutter field app offline-first. Web Django chỉ là backoffice/fallback online và không còn lưu nghiệp vụ trong `localStorage`.

## Bảo mật và offline

- Access/refresh token chỉ nằm trong `flutter_secure_storage`; app không lưu password.
- Khóa SQLCipher 256-bit sinh bằng `Random.secure()` và chỉ lưu trong secure storage.
- Task, room, checklist, queue, conflict và photo BLOB đều nằm trong database SQLCipher.
- Mỗi mutation/media có client UUID + idempotency key, base version, dependency và state `pending/syncing/synced/failed/conflict/discarded`.
- Sync tự chạy khi connectivity thay đổi nhưng vẫn bắt lỗi từng HTTP request; connectivity không được xem là bằng chứng có Internet.
- Version conflict không tự rebase. Màn hình yêu cầu người dùng bỏ local hoặc chủ động retry trên server version hiện tại.
- Complete bị disable khi task còn pending/failed/conflict.
- Cache được bind với user UUID trong SQLCipher; đổi tài khoản không thể đọc cache của người trước. Logout bị chặn khi còn unresolved work và secure-delete cache khi hoàn tất.

## UI hiện trường

- 7 tab: Việc của tôi, Chờ nhận, Đang làm, Chờ hỗ trợ, Chờ QC, Làm lại, Hoàn thành.
- Search và filter theo ngày/chi nhánh/tầng/loại phòng/task/ưu tiên/overdue/check-in risk; mỗi view có cache riêng.
- Danh sách tự lấy progress/version mới mỗi 30 giây khi online; countdown vẫn cập nhật cục bộ.
- Task card có countdown, cảnh báo chữ + icon, tiến độ/checklist/ảnh và sync state.
- Detail có task/room/booking/SLA, 9 typed checklist controls, ảnh local/server, vật tư/sự cố, QC/rework và timeline.
- Conflict sheet bắt buộc xem base/local/server trước khi discard hoặc explicit retry.
- Completion summary dùng blocker từ backend; offline chỉ queue và backend vẫn là nguồn validation cuối.

## Chạy và kiểm thử

Platform project Android/iOS đã được generate. Dùng Flutter 3.38+/Dart 3.10+:

```bash
cd housekeeping_app
flutter pub get
flutter analyze
flutter test
```

Các cấu hình bảo mật platform đã áp dụng:

- Android `minSdk` 24, `android:allowBackup="false"`, cleartext bị tắt ở release và ProGuard giữ SQLCipher.
- Release bật minify/resource shrinking, không dùng debug signing config.
- iOS có mô tả quyền camera/photo và Keychain entitlement cho secure storage.
- Build bằng `--dart-define=API_BASE_URL=https://<host>`; production chỉ dùng HTTPS.

## Luồng sync

1. Tải task list/detail online và cache vào SQLCipher.
2. Khi offline, queue checklist/note/pause/supply/issue/photo; photo bytes không ghi ra public storage.
3. Dependency planner gửi prerequisite và mutation phụ thuộc cùng batch theo đúng thứ tự.
4. Backend `/sync/batch` trả receipt riêng cho từng mutation.
5. `CONFLICT` giữ base/local/server snapshot để người dùng resolve; `FAILED` có nút retry.
6. Sau khi không còn dữ liệu unresolved, app mới cho gửi complete.
