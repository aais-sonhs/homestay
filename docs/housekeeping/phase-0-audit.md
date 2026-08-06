# Housekeeping — Báo cáo audit Giai đoạn 0

> Ngày audit: 05/08/2026 — Asia/Ho_Chi_Minh
> Nguồn yêu cầu: `README.md`
> Trạng thái: hoàn tất audit, chờ review trước Giai đoạn 1

## 1. Kết luận và cổng triển khai

MVP hiện tại là nền móng có thể tiến hóa, nhưng chưa đủ để tuyên bố đạt `AC-01`–`AC-30`. Không cần viết lại toàn bộ Django project; cần giữ các bảng hiện có, bổ sung model bằng migration tiến hóa, tách permission/selectors/state machine/service/API khỏi `views.py`, rồi xây field app offline-first.

Theo `PLAN.md` phần Giai đoạn 0 và “Việc Codex mới cần làm ngay” (`PLAN.md:306`, `PLAN.md:595`), chưa thay đổi nghiệp vụ hoặc database trước khi tài liệu này được review. Giai đoạn 1 chỉ bắt đầu sau khi chốt:

1. Dùng Flutter cho field app offline-first; web Django tiếp tục làm backoffice.
2. Mô hình role/scope theo permission matrix tại mục 5.
3. Mô hình dữ liệu và chuỗi migration tại mục 7.
4. Các policy mặc định tại mục 10.

## 2. Baseline đã kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| `python manage.py check` | Pass, 0 issue |
| `python manage.py makemigrations --check --dry-run` | Pass, không có model change chưa tạo migration |
| `python manage.py test` | Pass 32/32 test trong 9,350 giây |
| PostgreSQL local | Không ghi/xóa/reset dữ liệu trong audit |
| Fasthub | Chỉ đọc `/mnt/data/fasthub/`, không sửa |
| Deploy | Không khởi động app và không chiếm cổng `8020` |

32 test đang pass chỉ là regression baseline. Housekeeping mới có 14 test MVP (`housekeeping/tests.py:103`–`housekeeping/tests.py:292`), chưa có PostgreSQL concurrency test thật, offline E2E, SLA, notification hoặc permission matrix đầy đủ.

## 3. Audit source hiện tại

### 3.1. Thành phần nên giữ và tiến hóa

| Thành phần | Hiện trạng | Quyết định | Dẫn chiếu |
|---|---|---|---|
| Custom user | Có role, soft delete, access/refresh token | Giữ; bổ sung display name và Bearer auth adapter | `accounts/models.py:11`, `accounts/models.py:65` |
| Branch/membership | Scope chi nhánh và quyền ngoài ca cơ bản | Giữ bảng; bổ sung role tại chi nhánh, area/team/skill scope | `housekeeping/models.py:8`, `housekeeping/models.py:23` |
| Shift | Có một instance với start/end | Giữ; thêm shift assignment của người dùng | `housekeeping/models.py:36` |
| Room | Có trạng thái vận hành cơ bản | Giữ; bổ sung area FK, QR/GPS/Wi-Fi và access flags | `housekeeping/models.py:58` |
| Task | Có UUID, status, priority, version, timestamp và index scope | Giữ; bổ sung booking, assignment, SLA, progress metadata, rework metadata | `housekeeping/models.py:87` |
| Concurrency | `transaction.atomic`, `select_for_update`, optimistic version | Giữ pattern và đưa vào state machine tập trung | `housekeeping/services.py:156`, `housekeeping/services.py:183`, `housekeeping/services.py:429`, `housekeeping/services.py:473` |
| Checklist snapshot | Item đã được copy vào task, có đủ 9 enum type | Giữ dữ liệu; liên kết template/version/definition thật và thêm validation theo type | `housekeeping/models.py:159` |
| Media | Có ảnh, category, checklist link và client ID unique có điều kiện | Tiến hóa thành media đầy đủ metadata/sync state | `housekeeping/models.py:197` |
| Pause | Có interval paused/resumed | Giữ; thêm SLA inclusion, approval và computed duration | `housekeeping/models.py:226` |
| Supply/issue | Có quan hệ task/branch/room và idempotency cục bộ | Giữ; thêm destination/resolution/notification/attachments | `housekeeping/models.py:239`, `housekeeping/models.py:278` |
| QC | Có từng round riêng và unique `(task, round_number)` | Giữ dữ liệu; đổi domain thành QC round + failed item/media/rework round | `housekeeping/models.py:309` |
| History/activity | Có status history và context IP/device | Giữ; chuẩn hóa event và before/after payload | `housekeeping/models.py:331`, `housekeeping/models.py:345` |
| API envelope | Có `{success,data}` và error code cơ bản | Giữ contract ngoài; tách auth/serializer/API views | `housekeeping/views.py:49`, `housekeeping/views.py:181` |

### 3.2. Gap bắt buộc phải xử lý

| Nhóm | Gap và rủi ro | Mức | Hướng xử lý |
|---|---|---:|---|
| API authentication | Housekeeping API chỉ nhận Django session; chưa dùng `accounts.AccessToken`/Bearer | P0 | Bearer token auth cho field app, vẫn cho session auth ở backoffice |
| Role/scope | Không có Trưởng nhóm Housekeeping; `area` là chuỗi đơn; chưa có team/skill/shift assignment | P0 | Permission service duy nhất, membership role + scope quan hệ |
| State machine | Transition nằm rải trong service; chưa có allow-list tập trung; manager chưa create/reassign/cancel/priority | P0 | `state_machine.py` + action policy + room sync trong cùng transaction |
| Room verification | QR chỉ được kiểm tra “có value”, không đối chiếu phòng; chưa lưu GPS/Wi-Fi/guest consent | P0 | Verification policy và `TaskRoomVerification` bất biến |
| Booking | Chỉ có `booking_code`; không có check-out, guest count, guest-permission search | P1 | `Booking` thật, backfill từ code cũ |
| Checklist | `checklist_version` là text; type enum có nhưng service/UI coi gần như checkbox | P0 | Template/version/definition + typed validator + snapshot JSON |
| Failed item | `FAILED` luôn bị tính là incomplete; chưa có accepted reason hoặc ticket mapping | P0 | `failure_resolution`, accepted-by, issue FK và completion rule |
| Completion | Không chặn supply pending; không ghi lần lượt `COMPLETED` rồi `WAITING_QC`; thiếu summary endpoint | P0 | Completion validator + 2 history event trong một transaction |
| QC/rework | Chỉ reason/note; không có failed item, QC media, deadline, `rework_started_at`, rework round | P0 | QC round aggregate riêng, không ghi đè vòng cũ |
| Room safety | QC approve chuyển `READY` mà không kiểm tra lại blocking issue | P0 | Ready guard dùng chung cho non-QC và QC approve |
| SLA | Chỉ có `due_at` và derived overdue; không có acceptance/start deadline/escalation/pause policy | P1 | SLA policy/state/event engine và periodic command/job |
| Notification | Chưa có notification/outbox/read receipt | P1 | Transactional outbox + notification recipient/read model |
| Audit | Upload dùng `TASK_PHOTO_UPLOADED` thay vì `PHOTO_ADDED`; complete-to-QC thiếu `TASK_COMPLETED`; thiếu viewed/reassign/cancel | P0 | Enum 18 event README, helper ghi before/after |
| List/detail | Thiếu room type, check-in risk, QC rework/assignee filter, guest permission search, stable cursor/order tie-break | P1 | Selector/query object + indexed filters + page metadata |
| Realtime | Danh sách chỉ phản ánh khi reload | P1 | Polling delta endpoint trước; có thể nâng lên SSE/WebSocket sau |
| Offline | Dùng plaintext `localStorage`, chỉ queue checklist, không ảnh/note/issue/supply/pause | P0 | Flutter secure storage + encrypted SQLite + dependency queue |
| Idempotency | Chỉ ảnh/supply/issue có client ID; checklist và action khác có thể lặp | P0 | Receipt chung cho mọi mutation với unique user/key và payload hash |
| Test | SQLite test không kiểm chứng row lock; thiếu AC/TC trace | P0 | Unit/API/integration + PostgreSQL `TransactionTestCase` + mobile E2E |
| Deployment | `app.yaml` dùng `8020`, đang có nguy cơ xung đột dự án khác | Gate | Không deploy cho tới khi người dùng chọn port/dịch vụ |

### 3.3. Lỗi/điểm lệch cụ thể trong MVP

- `scoped_tasks()` cho Housekeeping chỉ thấy task của mình hoặc task `UNASSIGNED`; task `PENDING_ACCEPTANCE` được giao cho mình vẫn thấy qua nhánh `assignee=user`, nhưng chưa xét area/team/skill/shift (`housekeeping/services.py:68`).
- Thứ tự check-in đang xếp mọi task có `next_checkin_at`, không ưu tiên theo khoảng thời gian gần; thứ tự thiếu stable tie-break theo UUID (`housekeeping/services.py:79`).
- `accept_task()` kiểm tra ca của task, không kiểm tra assignment ca thực của user (`housekeeping/services.py:167`).
- `start_task()` không khóa `Room`, nên hai task khác nhau của cùng phòng vẫn có thể cùng bắt đầu (`housekeeping/services.py:184`).
- QR verification chỉ từ chối value rỗng, không so khớp QR của phòng (`housekeeping/services.py:193`).
- Checklist update chưa validate value theo 9 item type và chưa ghi riêng `TASK_PROGRESS_UPDATED` (`housekeeping/services.py:243`).
- Photo activity dùng tên ngoài danh sách README (`housekeeping/services.py:300`).
- Supply/issue mutation không nhận task version, nên không phát hiện stale client (`housekeeping/services.py:349`, `housekeeping/services.py:395`).
- Supply request tự chuyển toàn bộ task sang waiting support dù README cho phép tiếp tục checklist không bị ảnh hưởng (`housekeeping/services.py:385`).
- Completion chưa kiểm tra supply pending và failed-item resolution (`housekeeping/services.py:429`).
- Completion yêu cầu QC chuyển thẳng sang `WAITING_QC`; không có history `IN_PROGRESS → COMPLETED → WAITING_QC` (`housekeeping/services.py:459`).
- QC reject không lưu item/ảnh/deadline; QC approve không gọi shared room-ready guard (`housekeeping/services.py:473`).
- List API trả page cuối khi client yêu cầu page vượt range; contract ổn định hơn là trả list rỗng hoặc lỗi page rõ ràng (`housekeeping/views.py:293`).
- HTML filter không giữ selected state đầy đủ, thiếu tab/filter và không phân trang (`templates/housekeeping/task_list.html:10`).
- HTML checklist chỉ có nút “Xong”, chưa render control theo item type (`templates/housekeeping/task_detail.html:51`).
- Offline queue lưu plaintext ở `localStorage` và tự nối version tuyến tính, không có conflict UI (`templates/housekeeping/task_detail.html:122`).

## 4. Pattern tham chiếu từ Fasthub

### Nên tái sử dụng dưới dạng convention

- Tách role guard và queryset scoping thành hàm dùng chung như `common/access.py:19`–`common/access.py:175`.
- Bearer auth resolve token, gắn `request.user`, loại token revoked/user inactive như `common/api_auth.py:9`–`common/api_auth.py:43`; Homestay phải đồng thời kiểm tra `is_deleted`.
- Bảo toàn filter state và query phân trang như `common/list_views.py:69`–`common/list_views.py:133`.
- Snapshot checklist copy label/required/sort order khi aggregate được tạo như `operations/models.py:577`–`operations/models.py:651` và `operations/models.py:737`–`operations/models.py:843`.
- Gallery ảnh tách row và multipart service như `operations/models.py:1006`–`operations/models.py:1025`, `technician_app/lib/src/services/api_client.dart:73`–`technician_app/lib/src/services/api_client.dart:105`.
- Flutter service layer tách khỏi screen như `technician_app/lib/src/services/field_service.dart:13`–`technician_app/lib/src/services/field_service.dart:295`.
- QR scanner, camera sau, GPS capture và timestamp/location watermark là pattern UX hữu ích; server vẫn phải xác minh metadata, không tin client.
- Backoffice dùng responsive sidebar/topbar, filter form, pagination include và mobile table convention từ `templates/base.html`, `templates/operations/ticket_list.html`, `templates/operations/ticket_detail.html`.

### Không sao chép

- Không lưu username/password/token nhạy cảm bằng `SharedPreferences` như Fasthub field app hiện tại.
- Không gom API/workflow vào một `views.py` hàng nghìn dòng.
- Không dùng JSON checklist làm nguồn dữ liệu duy nhất; Homestay cần snapshot row để query/audit.
- Không cho state update trực tiếp thiếu state machine/version lock.
- Không dựa vào local path/photo state tạm thời mà thiếu encrypted queue và idempotency.

## 5. Permission matrix đề xuất

Ký hiệu: `✓` được phép trong scope; `C` theo cấu hình/quyền bổ sung; `—` mặc định không được phép.

| Hành động | Founder/Admin | Quản lý | Trưởng nhóm HK | Housekeeping | QC | Kho | Kỹ thuật | CSKH |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Xem task | ✓ toàn hệ thống | ✓ chi nhánh | ✓ team/area | ✓ của mình + open eligible | ✓ QC queue/đã tham gia | C task có supply | C task có issue | C read-only tối thiểu |
| Tìm dữ liệu khách | ✓ | ✓ | C | — | C | — | — | C |
| Tự nhận task | ✓ | C | ✓ | ✓ | — | — | — | — |
| Nhận ngoài ca | ✓ | ✓ | C | C | — | — | — | — |
| Từ chối/trả trước start | ✓ | ✓ | ✓ | C | — | — | — | — |
| Bắt đầu/rework | C | C | ✓ task của mình | ✓ task của mình | — | — | — | — |
| Checklist/note/photo | C | C | ✓ task của mình | ✓ task của mình | QC checklist/media | — | issue resolution media | — |
| Pause/resume | C | ✓ ngoại lệ | ✓ | ✓ task của mình | — | — | — | — |
| Báo supply/issue | ✓ | ✓ | ✓ | ✓ | C | — | — | — |
| Complete/send QC | C | C | ✓ task của mình | ✓ task của mình | — | — | — | — |
| Assign/reassign/handover | ✓ | ✓ chi nhánh | ✓ team/area | — | — | — | — | — |
| Create/cancel/change priority/SLA | ✓ | ✓ chi nhánh | C priority | — | — | — | — | — |
| QC approve/reject | ✓ | C theo policy | — | — | ✓ chi nhánh | — | — | — |
| Resolve supply | ✓ | ✓ | — | — | — | ✓ destination | — | — |
| Resolve issue | ✓ | ✓ | — | — | — | — | ✓ assigned queue | — |
| SLA dashboard | ✓ | ✓ chi nhánh | ✓ team | chỉ task của mình | QC metrics | supply metrics | issue metrics | — |
| Activity log | ✓ | ✓ chi nhánh | ✓ team/task | task đã tham gia | task QC | object liên quan | object liên quan | C read-only |

### Scope evaluation bắt buộc

1. User active, không soft-deleted.
2. Global role cho biết capability thô.
3. Active `BranchMembership` giới hạn chi nhánh và membership role.
4. Area/team/skill/shift assignment giới hạn task eligible.
5. Ownership/assignment và task state giới hạn mutation.
6. Policy cho phép ngoại lệ ngoài ca, return-after-start, QC-by-manager, guest search.
7. Mọi API selector và service đều gọi cùng permission layer; template không phải security boundary.

## 6. State transition table đề xuất

`OVERDUE` là cờ tính toán/SLA state, không phải trạng thái nghiệp vụ chính.

| Từ | Hành động | Đến | Actor | Guard chính | Side effect bắt buộc |
|---|---|---|---|---|---|
| — | create open task | `UNASSIGNED` | Manager/System | branch-room hợp lệ, không duplicate source | room `WAITING_CLEANING`, history/log |
| — | create assigned task | `ASSIGNED` hoặc `PENDING_ACCEPTANCE` | Manager/System | assignee eligible | assignment history, notify assignee |
| `ASSIGNED` | request acknowledgement | `PENDING_ACCEPTANCE` | System/Manager | assignee tồn tại | acceptance SLA bắt đầu |
| `UNASSIGNED`, `PENDING_ACCEPTANCE` | accept | `ACCEPTED` | HK/Lead | scope, shift, capacity, version, unlocked | row lock, assignee/accepted_at, log/notify |
| `ASSIGNED`, `PENDING_ACCEPTANCE` | reject | `UNASSIGNED` | Assignee | reason bắt buộc | close assignment, log `TASK_REJECTED`, notify |
| `ACCEPTED` | return | `UNASSIGNED` | Assignee/Lead | policy cho phép, reason bắt buộc | close assignment, log `TASK_RETURNED` |
| `ACCEPTED` | start | `IN_PROGRESS` | Assignee | room verification, guest consent, no active room task | lock task + room, started_at, room `CLEANING` |
| `QC_REJECTED` | start rework | `IN_PROGRESS` | Assignee | active rejected QC round, scope/version | create `ReworkRound`, rework_started_at/count, room `CLEANING` |
| `IN_PROGRESS` | pause | `PAUSED` | Assignee | reason bắt buộc | open pause interval, SLA policy, log/notify |
| `IN_PROGRESS` | blocking wait | `WAITING_SUPPORT` | Assignee/System | blocking supply/issue/reason | open pause interval, room `CLEANING_BLOCKED` |
| `PAUSED`, `WAITING_SUPPORT` | resume | `IN_PROGRESS` | Assignee/Lead | blockers resolved/approved | close pause, room `CLEANING`, log |
| `IN_PROGRESS` | complete (QC) | `COMPLETED` rồi `WAITING_QC` | Assignee | checklist/photo/failed/supply/issue/sync/final confirm | hai history event, completed_at, QC round, room `WAITING_QC`, notify QC |
| `IN_PROGRESS` | complete (no QC) | `COMPLETED` rồi `QC_APPROVED` | Assignee | cùng completion guard + room-ready guard | room `READY`, hai history event |
| `WAITING_QC` | approve | `QC_APPROVED` | QC | version, QC checklist, no blocking issue | close QC round, room `READY`, notify |
| `WAITING_QC` | reject | `QC_REJECTED` | QC | reason + failed items, deadline | close QC round immutable, room `REWORK_REQUIRED`, notify HK |
| trạng thái chưa kết thúc | reassign | state phù hợp (`PENDING_ACCEPTANCE` mặc định) | Manager/Lead | scope và handover policy | close/open assignment, preserve progress, `TASK_REASSIGNED` |
| `IN_PROGRESS`/paused | handover | `PENDING_ACCEPTANCE` hoặc `ACCEPTED` | Manager/Lead | ca kết thúc, recipient eligible | `TaskHandover`, preserve snapshot/media, optional re-confirm items |
| trạng thái chưa kết thúc | cancel | `CANCELLED` | Manager/Admin | reason, replacement/room recalculation | close pause/assignment, recompute room, notify/log |

Transition không có trong bảng phải bị từ chối bằng `TASK_INVALID_STATUS`. Timestamp hệ thống (`accepted_at`, `started_at`, `completed_at`, history time) không nhận từ payload người dùng.

## 7. Data model và migration proposal

### 7.1. Aggregate/scope

| Model | Thay đổi đề xuất |
|---|---|
| `Branch` | Giữ; liên kết `BranchHousekeepingPolicy` và supply destination |
| `Area` | FK branch, code/name/floor range; unique `(branch, code)` |
| `HousekeepingTeam` | FK branch, lead, active; M2M area/skill |
| `BranchMembership` | Thêm `membership_role`, team/areas/skills quan hệ; giữ 2 boolean cũ trong giai đoạn tương thích |
| `Skill` | code/name, branch nullable cho skill dùng chung |
| `Shift` | Giữ instance ca hiện có |
| `ShiftAssignment` | user, shift, team/area, overtime/active; unique user-shift |
| `Room` | Thêm `area` FK nullable ban đầu, QR identifier hash, lat/lng/radius, allowed Wi-Fi identifiers, access/guest/lock flags |
| `Booking` | branch, room, code, check-in/out, guest count, guest fields, special requests, status; guest fields có permission riêng |

### 7.2. Task/workflow

| Model | Thay đổi đề xuất |
|---|---|
| `HousekeepingTask` | booking FK, assigned_by, team, acceptance/start deadline, standard duration, last_progress_at, updated_by, rework_started_at, current round, cancellation fields, risk fields; giữ `version` |
| `TaskAssignment` | assignee, assigned_by, shift/team, start/end, reason, accepted/rejected/returned timestamps |
| `TaskHandover` | from/to assignment/user/shift, note, re-confirm policy snapshot |
| `TaskRoomVerification` | method, submitted/server value hash, GPS/accuracy/Wi-Fi, guest consent/note, verified result/time/device |
| `TaskStatusHistory` | Giữ; thêm structured metadata/version nếu cần |
| `HousekeepingActivityLog` | Enum event chuẩn, reason, before/after, request/idempotency correlation ID |

### 7.3. Checklist/media/support/QC

| Model | Thay đổi đề xuất |
|---|---|
| `ChecklistTemplate` | branch/task type/name/active |
| `ChecklistVersion` | template, version number, status/published_at, policy snapshot; immutable sau publish |
| `ChecklistItemDefinition` | version, key/group/title/type/options/validation/required/photo count/sort |
| `TaskChecklistItem` | Giữ snapshot row; thêm definition FK nullable, options/validation snapshot, failure resolution/issue link/update version |
| `TaskMedia` | Tiến hóa từ `TaskPhoto`: task/room/user/checklist/QC/issue/supply, category, captured/uploaded time, GPS, source, checksum, client UUID, sync state |
| `TaskPause` | Thêm previous status, SLA inclusion, approved_by, resumed reason, duration |
| `SupplyLocation` | branch/warehouse code/name/recipient group |
| `SupplyRequest` | destination FK, blocking flag, resolution/fulfilled metadata, version; item rows giữ nguyên |
| `IssueTicket` | booking FK, room asset/device reference, assignment/resolution/SLA; attachment relation |
| `QCRound` | Tiến hóa `QCTask`, immutable result, deadline, checklist snapshot, reviewer timestamps |
| `QCFailedItem` | QC round → task checklist item, reason/note/rework required/resolved round |
| `QCMedia` | QC round/media association |
| `ReworkRound` | source QC round, scope policy, started/completed/sent timestamps, assignee |

### 7.4. SLA/notification/offline

| Model | Mục đích |
|---|---|
| `SLAPolicy` | Deadline/duration/risk thresholds và pause inclusion theo branch/task type/priority |
| `TaskSLAState` | Snapshot policy/deadline, accumulated active/pause time, breach flags |
| `SLAEscalationEvent` | milestone 5/15/30/risk, dedupe key, delivered state |
| `Notification` | type/title/body/object/branch, created/read state |
| `NotificationRecipient` | notification-user, read/delivered timestamps |
| `OutboxEvent` | transactional delivery, attempts/next retry/processed/error |
| `OfflineMutationReceipt` | user/task/idempotency key, operation, payload hash, base/result version, response/status/conflict; unique `(user, idempotency_key)` |

### 7.5. Chuỗi migration không mất dữ liệu

1. **`0002_domain_foundation`**: chỉ thêm model và field nullable/default an toàn; chưa xóa/rename field cũ.
2. **`0003_backfill_legacy_housekeeping`**:
   - Tạo `Area` theo `(branch, Room.area)` và gắn `Room.area_fk`.
   - Tạo legacy `Booking` theo `(branch, booking_code)` rồi gắn task.
   - Tạo legacy checklist template/version theo `(branch, task_type, checklist_version)`; tạo definition từ các snapshot key hiện có và gắn item.
   - Tạo current `TaskAssignment` từ `assignee/accepted_at/shift`; không suy diễn timestamp không tồn tại.
   - Backfill media room/user/captured_at từ task/uploaded_by/created_at.
   - Giữ nguyên mọi `QCTask`/round/reason/note; tạo rework record chỉ khi có bằng chứng từ history.
   - Khởi tạo SLA state từ deadline hiện có nhưng đánh dấu `legacy_backfill` để không phát notification lịch sử.
3. **`0004_constraints_and_indexes`**: sau kiểm tra backfill mới thêm FK non-null phù hợp, check constraint, partial unique/index.
4. **`0005_legacy_compatibility_cleanup`**: chỉ xóa field text cũ ở một release sau, sau khi dual-read/dual-write và backup được xác nhận.

Index/constraint tối thiểu:

- Task: `(branch, status, due_at, id)`, `(shift, status, scheduled_start_at)`, `(assignee, status, due_at)`, `(room, status)`.
- Partial unique để chỉ có một active cleaning task mỗi room nếu policy không cho song song.
- Checklist definition unique `(version, key)`; snapshot unique `(task, definition_key)`.
- QC/rework unique `(task, round_number)`.
- Notification recipient `(user, read_at, created_at)`.
- Offline receipt unique `(user, idempotency_key)` và lưu payload hash để phát hiện tái dùng key sai payload.

## 8. API contract checklist

### 8.1. Quy ước chung

- Base `/api/v1/housekeeping`.
- Field app: `Authorization: Bearer <token>`; backoffice có thể dùng session + CSRF.
- Mutation yêu cầu `version` và `Idempotency-Key` (client UUID); server trả `version` mới.
- Success: `{ "success": true, "data": ..., "pagination": ... }`.
- Error: `{ "success": false, "code": ..., "message": ..., "details": ..., "correlationId": ... }`.
- Conflict trả HTTP 409, `currentVersion`, server snapshot và local operation metadata.
- List dùng stable order với `id` làm tie-break; pagination phải giữ filter state.

### 8.2. Endpoint bắt buộc

| Endpoint | Contract cần chốt |
|---|---|
| `GET /tasks` | date/shift/branch/area/floor/roomType/type/status/priority/assignee/overdue/checkinRisk/qcRework/q/tab/page/limit |
| `GET /tasks/{id}` | room/booking/SLA/assignment/checklist/media/support/QC/rework/timeline/capabilities |
| `POST /tasks/{id}/accept` | version + idempotency; row lock; `TASK_ALREADY_ASSIGNED` |
| `POST /tasks/{id}/reject` | reason/note/version |
| `POST /tasks/{id}/return` | reason/note/version |
| `POST /tasks/{id}/start` | verification methods, GPS/Wi-Fi, guest consent, version |
| `PATCH /tasks/{id}/checklist-items/{itemId}` | typed value/status/note/failure resolution/version |
| `POST /tasks/{id}/media` | multipart, client UUID/checksum/category/captured metadata/version |
| `POST /tasks/{id}/pause` | reason/note/media/version |
| `POST /tasks/{id}/resume` | version, blocker validation |
| `POST /tasks/{id}/supply-requests` | destination/items/priority/blocking/client UUID/version |
| `POST /tasks/{id}/issues` | room/booking/device/type/severity/blocking/attachments/client UUID/version |
| `GET /tasks/{id}/completion-summary` | duration/checklist/media/supply/issues/pending sync/blockers |
| `POST /tasks/{id}/complete` | final confirm/note/version/idempotency; atomic QC creation |
| `POST /tasks/{id}/rework/start` | source QC round/version |
| `POST /tasks/{id}/qc-rounds/{round}/review` | approve hoặc reason+failedItems+media+deadline/version |
| `POST /tasks/{id}/reassign` | assignee/shift/reason/version |
| `POST /tasks/{id}/handover` | recipient/shift/note/reconfirm policy/version |
| `POST /tasks/{id}/cancel` | reason/replacement/version |
| `PATCH /tasks/{id}/priority` | priority/reason/version |
| `GET/PATCH /supply-requests` | queue và fulfill/cancel scoped cho Kho |
| `GET/PATCH /issues` | queue và assign/resolve scoped cho Kỹ thuật |
| `GET /notifications`, `POST /notifications/{id}/read` | recipient scope/read receipt |
| `POST /sync/batch` | ordered mutations, per-item receipt/result/conflict; không partial overwrite |
| `GET /sync/conflicts/{id}` | server/local/base snapshots và resolution options |
| `GET /dashboard/sla`, `GET /dashboard/performance` | branch/team/shift/date scope |

Giữ toàn bộ error code ở README mục 28 (`README.md:1190`) và bổ sung có kiểm soát: `ROOM_ALREADY_IN_PROGRESS`, `GUEST_CONSENT_REQUIRED`, `INVALID_CHECKLIST_VALUE`, `FAILED_ITEM_UNRESOLVED`, `PENDING_SYNC_EXISTS`, `IDEMPOTENCY_KEY_REUSED`.

## 9. Quyết định field app/offline

### Đề xuất: Flutter field app + Django backoffice

Flutter là lựa chọn phù hợp hơn PWA cho yêu cầu camera bắt buộc, QR, GPS, secure token, encrypted local database, photo blob/path, background sync và conflict screen. Fasthub Flutter đã có API client, service layer, list/detail, camera/GPS/QR và image timestamp để tham khảo; Homestay cần thay phần session storage và bổ sung offline engine.

Kiến trúc client đề xuất:

- `flutter_secure_storage` cho access/refresh token.
- SQLCipher-backed SQLite/Drift cho cached task, room, checklist, mutation queue và conflict.
- App-private encrypted file storage cho ảnh chờ sync; checksum + client UUID.
- Queue theo dependency: checklist/note → media/issue/supply → complete.
- Trạng thái `synced/pending/failed/conflict` trên từng mutation/media.
- Background sync khi có mạng, foreground retry rõ ràng; không tự resolve version conflict.
- Không lưu password; không cho final complete khi required mutation còn pending theo policy mặc định.

Web Django hiện tại được giữ cho backoffice và làm fallback online; không dùng `localStorage` làm giải pháp offline nghiệp vụ.

## 10. Policy/configuration cần chốt

Đề xuất default an toàn để không chặn thiết kế Giai đoạn 1:

| Policy | Default đề xuất |
|---|---|
| Ngoài ca | Tắt; chỉ membership/manager override |
| Concurrent task | 3, kế thừa setting hiện tại; policy theo branch có thể override |
| Return sau start | Tắt; chỉ manager/lead handover |
| Active task cùng room | 1 |
| Verification | Cấu hình theo branch/task type; QR phải so khớp room nếu bật |
| Guest in room | Bắt buộc consent + note trước start |
| Camera-only evidence | Bật cho ảnh bắt buộc; gallery chỉ cho category được phép |
| Failed checklist | Phải có issue hoặc accepted reason do role được phép duyệt |
| Supply pending | Blocking request chặn complete; non-blocking không chặn |
| Pause SLA | Chỉ loại trừ reason được policy đánh dấu và có interval đóng/mở rõ ràng |
| QC | Bật theo task type; checkout/check-in preparation mặc định cần QC |
| Rework scope | Chỉ failed items + final inspection; manager có thể yêu cầu full checklist |
| Offline complete | Tắt khi required mutation/media còn pending |
| Check-in risk | Cảnh báo theo standard remaining duration + buffer 15 phút |
| Realtime phase đầu | Poll delta 15–30 giây; đánh giá SSE sau |

## 11. Thứ tự triển khai sau review

1. Giai đoạn 1: model + additive/backfill migrations + migration tests.
2. Giai đoạn 2: permission selectors + state machine + PostgreSQL concurrency/idempotency tests.
3. Giai đoạn 3–5: API, execution flow, QC/rework và integration tests.
4. Giai đoạn 6: SLA/outbox/notifications/dashboard.
5. Giai đoạn 7: Flutter offline-first app.
6. Giai đoạn 8: backoffice/field UX hoàn chỉnh.
7. Giai đoạn 9: AC/TC evidence, PostgreSQL smoke, migration rehearsal; deploy chỉ sau khi xử lý port `8020`.

Ma trận từng AC/TC và test target nằm tại `docs/housekeeping/requirements-traceability.md`.
