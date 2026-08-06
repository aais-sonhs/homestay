# Housekeeping — Kết quả Giai đoạn 3

> Hoàn tất: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

API Housekeeping đã được tách hoàn toàn khỏi backoffice view. `housekeeping/views.py` chỉ còn session-authenticated HTML; contract JSON v1 nằm trong `housekeeping/api/`.

Các phần đã triển khai:

- Bearer authentication cho field app và session + CSRF cho backoffice.
- Token login, refresh rotation và logout tại `/api/v1/auth/*`.
- Access token TTL 1 giờ; refresh token TTL 30 ngày; token revoked/expired và user bị khóa/xóa bị từ chối.
- Error envelope thống nhất có `code`, `details`, `correlationId` và HTTP status.
- Task list/detail/completion summary, capability map và dữ liệu assignment/checklist/media/support/QC/rework/SLA/timeline.
- Default ngày + shift assignment thực; cho phép chọn ca khác rõ ràng.
- Filter branch/area/floor/room type/type/status/priority/assignee/overdue/check-in risk/QC rework/tab/search.
- Thứ tự QC rework → check-in gần → overdue → urgent → assigned → deadline → code → ID.
- Pagination ổn định; trang vượt phạm vi trả mảng rỗng thay vì tự nhảy về trang cuối.
- Mutation bắt buộc optimistic `version` và `Idempotency-Key`, có replay response và phát hiện key dùng sai payload.
- Checksum nội dung ảnh nằm trong idempotency payload và metadata media.

## Endpoint đã có

- `GET /api/v1/housekeeping/tasks`
- `GET /api/v1/housekeeping/tasks/{taskId}`
- `GET /api/v1/housekeeping/tasks/{taskId}/completion-summary`
- `POST .../accept|start|reject|return|pause|resume|complete|cancel`
- `PATCH .../checklist-items/{itemId}`
- `POST .../supply-requests|issues|media`
- `POST .../reassign|handover|rework/start`
- `PATCH .../priority`
- `POST .../qc-review`
- `POST .../qc-rounds/{round}/review`

Các URL slashless theo contract README và vẫn chấp nhận trailing slash để tương thích MVP.

## Security boundary

- Request có `Authorization: Bearer ...` không dùng cookie và được miễn CSRF sau khi middleware nhận diện header; token vẫn phải hợp lệ trong API decorator.
- Request không có Authorization dùng Django session và tiếp tục bắt buộc CSRF.
- Explicit Authorization sai không được fallback sang session cookie.
- Detail ngoài scope trả `TASK_NOT_FOUND` để không lộ dữ liệu; mutation ngoài branch trả `USER_BRANCH_NOT_ALLOWED` theo TC-05.
- Guest name/phone chỉ được search/serialize cho role quản lý/founder/admin/CSKH.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| API contract/security tests | 14/14 pass |
| Toàn bộ suite SQLite | 62 test: 61 pass, 1 concurrency skip |
| PostgreSQL row-lock concurrency | 1/1 pass trên `test_homestay` |

## Phân pha còn lại

- QC failed-item/media/deadline và rework round đầy đủ: Giai đoạn 5.
- Notification list/read và support recipients: Giai đoạn 6.
- Offline sync batch/conflict detail: Giai đoạn 8.
- Supply/issue fulfillment queues hoàn chỉnh: Giai đoạn 4 và 6.

Không migration/reset/ghi dữ liệu vào database nghiệp vụ `homestay`; test PostgreSQL chỉ tạo rồi xóa `test_homestay`.
