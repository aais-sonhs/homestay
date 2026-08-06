# Housekeeping — Kết quả Giai đoạn 4

> Hoàn tất backend: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

Luồng thực hiện task từ nhận/bắt đầu đến completion validation đã được khép kín ở backend và API.

### Checklist

- Validate/normalize đủ `CHECKBOX`, `YES_NO`, `NUMBER`, `TEXT`, `PHOTO`, `SINGLE_SELECT`, `MULTI_SELECT`, `DEVICE_CHECK`, `QR_SCAN`.
- Snapshot options/validation được dùng; hỗ trợ min/max, length/pattern, selection count, expected hash/value và required photo count.
- Task version và item version phát hiện hai cập nhật song song.
- Item `FAILED` phải có reason hoặc issue; manager/lead có endpoint chấp thuận ngoại lệ, mọi sửa đổi sau đó làm mất chấp thuận cũ.
- Progress, `last_progress_at`, `updated_by` và activity event được cập nhật tự động.

### Xác minh phòng và media

- Một policy có thể đồng thời yêu cầu QR, GPS, Wi-Fi và ảnh camera trước khi dọn.
- GPS kiểm tra range, accuracy và bán kính Haversine quanh tọa độ phòng.
- QR chỉ lưu hash; Wi-Fi so với allow-list; camera verification chỉ nhận ảnh `BEFORE` chụp bằng camera của đúng user/task.
- Phòng có khách bắt buộc consent theo policy và lưu note trong verification record.
- Media lưu checksum, source, captured time, GPS/accuracy, device, metadata và link checklist/issue/supply.
- Policy có thể cấm gallery đối với ảnh bằng chứng bắt buộc.

### Pause, support và completion

- Pause reason theo allow-list README; `OTHER` bắt buộc note.
- Pause support chuyển `WAITING_SUPPORT`; resume chặn mọi blocking issue chưa resolved/cancelled.
- SLA state cộng riêng `excluded_pause_seconds` khi resume.
- Kho và Kỹ thuật có queue theo branch; support item có version, transition guard và activity log.
- Supply fulfilled/issue resolved làm mất blocker; nhân viên chủ động resume task.
- `completion-summary` và `complete` gọi cùng một validator cho pending checklist, failed item, số ảnh synced, blocking issue, pending supply và pending offline/media sync.
- Receipt của chính request `complete` được loại khỏi pending-sync query để request không tự chặn.
- Trả task sau start mặc định bị cấm; khi branch policy cho phép thì giữ progress/history và không đưa phòng về `READY`.

## Migration

`0004_execution_verification_policy.py` chỉ thêm hai cờ boolean mặc định `False` và mở rộng choice verification; không xóa/đổi dữ liệu hiện có.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Phase 4 integration tests | 10/10 pass |
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Toàn bộ suite SQLite | 72 test: 71 pass, 1 concurrency skip |
| PostgreSQL row-lock concurrency | 1/1 pass trên `test_homestay` |

UI mobile cho typed controls/camera/offline queue vẫn thuộc Giai đoạn 7–8; trạng thái “hoàn tất backend” không đồng nghĩa field app đã hoàn thành.
