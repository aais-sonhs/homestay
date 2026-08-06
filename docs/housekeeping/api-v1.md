# Housekeeping API v1

Base URL: `/api/v1/housekeeping`

## Xác thực

Field app gửi `Authorization: Bearer <accessToken>`. Backoffice có thể dùng Django session và CSRF token.

- `POST /api/v1/auth/login`: `identifier`, `password`, `deviceName`.
- `POST /api/v1/auth/refresh`: `refreshToken`, `deviceName`.
- `POST /api/v1/auth/logout`: Bearer access token và tùy chọn `refreshToken`.

## Quy ước mutation

Mọi task mutation gửi:

- `version` hiện tại trong body.
- `Idempotency-Key` duy nhất trong header.
- Tùy chọn `X-Request-ID`; server tự tạo nếu thiếu.

Key được gửi lại với cùng operation/payload sẽ replay kết quả, response có header `Idempotent-Replayed: true`. Dùng cùng key cho payload khác trả HTTP 409 `IDEMPOTENCY_KEY_REUSED`.

## Response

Success:

```json
{"success": true, "data": {}, "correlationId": "..."}
```

Error:

```json
{"success": false, "code": "TASK_VERSION_CONFLICT", "message": "...", "details": {}, "correlationId": "..."}
```

## Task query

`GET /tasks` hỗ trợ `date`, `dateFrom`, `dateTo`, `shiftId`, `branchId`, `area`, `floor`, `roomType`, `taskType`, `status`, `priority`, `assignee`, `overdue`, `checkinRisk`, `qcRework`, `tab`, `q`, `page`, `limit`.

`status`, `taskType` và `priority` chấp nhận danh sách phân cách bởi dấu phẩy. `assignee` nhận `me`, `unassigned`, user UUID hoặc username. `limit` từ 1 đến 100.

## Tạo task

`POST /tasks` dành cho Founder/Admin/Manager, bắt buộc `Idempotency-Key`. Payload gồm `branchId`, `roomId`, `taskType`, `scheduledStartAt`, `dueAt`; có thể truyền `code`, `bookingId`, `priority`, `assigneeId`, `shiftId`, `areaId`, `teamId`, `checklistVersionId`, `requiredSkillIds`, `nextCheckinAt`, `standardDurationMinutes`, `requiresQc`, `guestInRoom`, `specialRequest` và `note`.

Server kiểm tra scope chi nhánh/phòng/booking/ca/khu vực/nhóm, snapshot checklist đã phát hành, ràng buộc đủ kỹ năng của assignee, tạo assignment/history/activity/SLA state, đồng bộ trạng thái phòng và gửi notification trong cùng transaction. Replay cùng key và payload trả task đã tạo, không tạo bản ghi trùng.

## Task mutation

- `POST /tasks/{id}/accept`
- `POST /tasks/{id}/start`
- `POST /tasks/{id}/reject`
- `POST /tasks/{id}/return`
- `PATCH /tasks/{id}/note`
- `PATCH /tasks/{id}/checklist-items/{itemId}`
- `POST /tasks/{id}/pause`
- `POST /tasks/{id}/resume`
- `POST /tasks/{id}/supply-requests`
- `POST /tasks/{id}/issues`
- `POST /tasks/{id}/media`
- `POST /tasks/{id}/complete`
- `POST /tasks/{id}/reassign`
- `POST /tasks/{id}/handover`
- `PATCH /tasks/{id}/priority`
- `POST /tasks/{id}/cancel`
- `POST /tasks/{id}/rework/start`
- `POST /tasks/{id}/qc-rounds/{round}/review`

## Offline sync

### Gửi batch mutation

`POST /sync/batch` nhận tối đa 100 mutation. Mỗi phần tử có contract:

```json
{
  "clientMutationId": "uuid-client",
  "idempotencyKey": "uuid-idempotency",
  "operation": "UPDATE_CHECKLIST_ITEM",
  "taskId": "uuid-task",
  "baseVersion": 3,
  "baseSnapshot": {"version": 3},
  "dependsOn": ["uuid-mutation-truoc"],
  "payload": {"itemId": "uuid-item", "status": "COMPLETED", "value": true}
}
```

Operation hỗ trợ: `ACCEPT`, `START`, `UPDATE_CHECKLIST_ITEM`, `UPDATE_TASK_NOTE`, `PAUSE`, `RESUME`, `CREATE_SUPPLY_REQUEST`, `REPORT_ISSUE`, `COMPLETE`.

Server topological-sort theo `dependsOn`, xử lý mỗi mutation độc lập và trả đúng thứ tự đầu vào. Một lỗi không rollback mutation độc lập khác. Mỗi result có `status` là `SYNCED`, `FAILED`, `CONFLICT`, `BLOCKED` hoặc `DISCARDED`, cùng `receiptId`, `replayed`, `result`, `error` và `conflict` tương ứng.

`baseVersion` phải khớp chính xác version server tại thời điểm chạy. Server không tự rebase hoặc ghi đè. Conflict lưu đủ `baseSnapshot`, local operation/payload và `serverSnapshot`.

### Xem và giải quyết conflict

- `GET /sync/conflicts/{receiptId}`: chỉ chủ receipt còn scope trên task mới xem được.
- `POST /sync/conflicts/{receiptId}/resolve`: cần `Idempotency-Key` cho chính thao tác resolve.

Bỏ thay đổi local:

```json
{"action": "DISCARD_LOCAL"}
```

Retry rõ ràng trên version server hiện tại:

```json
{
  "action": "RETRY_WITH_SERVER_VERSION",
  "newIdempotencyKey": "uuid-moi",
  "clientMutationId": "uuid-mutation-moi"
}
```

`newIdempotencyKey` phải khác key resolve. Kết quả mutation mới nằm trong `data.retry`; receipt cũ chuyển `DISCARDED` và giữ resolution audit.

### Bỏ receipt thất bại

`POST /sync/receipts/{receiptId}/discard` cần `Idempotency-Key`. Endpoint áp dụng cho receipt `FAILED` hoặc `CONFLICT`, giữ lại audit và loại receipt khỏi completion blocker.

Client phải giữ mutation/media `pending`, `failed` hoặc `conflict` cho đến khi có kết quả rõ ràng. Không được coi trạng thái connectivity là bằng chứng request đã tới server; replay bằng cùng idempotency key là cách khôi phục an toàn.

## Web backoffice

Các route session-authenticated dùng chung selector/service/permission với API:

- `/housekeeping/tasks/`: tabs, search và filter vận hành.
- `/housekeeping/tasks/create/`: tạo task, chọn checklist/kỹ năng và phân công theo scope.
- `/housekeeping/operations/`: team progress, QC queue, SLA/check-in risk và performance.
- `/housekeeping/support/`: Kho/Kỹ thuật queue; mutation dùng entity version.
- `/housekeeping/activity/`: audit log theo task scope.
- `/housekeeping/notifications/`: notification center theo recipient.

Web không lưu business queue offline. Khi mất mạng, người dùng được hướng sang Flutter field app.

QC reject body gửi `approved: false`, general `reason`/`note`, `deadlineAt`, `mediaIds` và `failedItems[]` gồm `checklistItemId`, `reasonCode`, `reason`, `note`, `reworkRequired`. QC approve gửi `approved: true`.

Checklist failed-item exception:

- `POST /tasks/{id}/checklist-items/{itemId}/accept-failure`

Support queues:

- `GET /supply-requests`, `PATCH /supply-requests/{requestId}` cho Kho/Quản lý.
- `GET /issues`, `PATCH /issues/{issueId}` cho Kỹ thuật/Quản lý.

## Notification

- `GET /notifications`: phân trang, hỗ trợ `unread=true|false`, `type`, `branchId`.
- `POST /notifications/{recipientId}/read`: cần `Idempotency-Key`; không cần task version và chỉ user nhận thông báo mới đọc được.

Notification được tạo cùng transaction nghiệp vụ. `OutboxEvent.deduplication_key` ngăn gửi lặp khi evaluator hoặc mutation được chạy lại.

## SLA và dashboard

- `GET /dashboard/sla`: tổng hợp near-due, overdue, check-in risk, breach theo acceptance/start/completion và danh sách task rủi ro.
- `GET /dashboard/performance`: hiệu suất nhóm theo nhân viên/ca/chi nhánh, gồm completion/QC rate, SLA breach, active/pause duration và rework rounds.

Hai dashboard hỗ trợ cùng filter task; nếu không truyền `date`, `dateFrom` hoặc `dateTo`, server dùng ngày hiện tại.

Job định kỳ chạy:

```bash
python manage.py evaluate_housekeeping_sla --limit 1000
```

Có thể giới hạn bằng `--branch <UUID|code>` hoặc `--task-id <UUID>`. Job chụp policy snapshot, đánh dấu breach, nâng task có check-in risk lên `URGENT`, rồi tạo escalation 5/15/30 phút có dedupe.

`startup.sh` bật evaluator theo chu kỳ mặc định 60 giây cùng tiến trình web. Có thể cấu hình `ENABLE_SLA_WORKER=0` hoặc `SLA_INTERVAL_SECONDS=<giây>` khi hạ tầng dùng scheduler riêng.
