# Housekeeping — Kết quả Giai đoạn 7

> Hoàn tất backend + Flutter MVP: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

- Backend có batch sync tối đa 100 mutation, topological order theo `dependsOn`, per-item receipt/result và lỗi độc lập.
- Mọi mutation dùng client UUID, idempotency key và exact `baseVersion`; replay không tạo dữ liệu trùng.
- Conflict không tự rebase. Receipt giữ base snapshot, local operation/payload và server snapshot để người dùng chủ động discard hoặc retry.
- Retry dùng idempotency key mới trên server version hiện tại; receipt cũ giữ trạng thái `DISCARDED` cùng resolution audit.
- Completion blocker nhận biết receipt `RECEIVED`, `FAILED` và `CONFLICT` chưa xử lý.
- Flutter field app cache task/detail và toàn bộ queue trong SQLCipher; access/refresh token và khóa database nằm trong secure storage.
- Ảnh offline được giữ dưới dạng BLOB mã hóa kèm checksum và metadata, không ghi vào public/shared storage.
- Dependency planner gửi mutation theo đúng thứ tự; reconnect trigger sync nhưng mọi request vẫn bắt network/API failure riêng.
- UI có trạng thái pending/failed/conflict, retry/discard và so sánh base/local/server; complete bị disable khi còn unresolved data.
- Android/iOS platform project đã được tạo và harden cho backup, cleartext, release minification, camera và Keychain.
- Web fallback không còn dùng `localStorage` cho queue nghiệp vụ.

## API

- `PATCH /api/v1/housekeeping/tasks/{taskId}/note`
- `POST /api/v1/housekeeping/sync/batch`
- `GET /api/v1/housekeeping/sync/conflicts/{receiptId}`
- `POST /api/v1/housekeeping/sync/conflicts/{receiptId}/resolve`
- `POST /api/v1/housekeeping/sync/receipts/{receiptId}/discard`

Chi tiết request/response và resolution contract nằm trong `docs/housekeeping/api-v1.md`.

## Kiểm chứng

`test_phase7_offline_sync.py` bao phủ:

1. Ordered batch và replay không tạo bản ghi trùng.
2. Conflict giữ base/local/server snapshot và block dependency.
3. Scope conflict theo user/branch.
4. Discard conflict idempotent.
5. Explicit retry trên server version hiện tại và replay idempotent.
6. Direct note mutation dùng cùng idempotency contract.
7. Mutation lỗi không rollback item độc lập và có thể discard.
8. Static security contract: không business `localStorage`, dùng secure storage/SQLCipher/photo BLOB.

Flutter kiểm chứng bằng `flutter analyze` và unit test cho dependency order, cycle rejection và server sync-state mapping.

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Phase 7 backend/security contract | 8/8 pass |
| Toàn bộ Django suite SQLite | 86 test: 85 pass, 1 PostgreSQL-only skip |
| PostgreSQL row-lock concurrency | 1/1 pass trên `test_homestay` |
| Flutter analyze | Pass, 0 issue |
| Flutter unit test | 3/3 pass |

## Phần chuyển sang Giai đoạn 9

- Widget test cho màn hình conflict/failure và completion blocker.
- Device/integration E2E: offline checklist + camera, kill/restart app, reconnect, replay và conflict resolve.
- Android/iOS release build/signing trên toolchain CI thực tế.
