# KẾ HOẠCH TRIỂN KHAI HOUSEKEEPING VÀ TÀI LIỆU BÀN GIAO CODEX

> Phạm vi mở rộng sau Housekeeping được ghi tại
> `docs/product/operations-platform-requirements.md`. Từ 07/08/2026, roadmap sản phẩm
> tiếp tục với trung tâm vận hành phòng: lịch Booking, readiness, phòng 360°, bảo trì,
> kho, stop-sell và dashboard đa vai trò. Yêu cầu Housekeeping trong tài liệu này vẫn
> là nền tảng bắt buộc và không bị thay thế.

> Cập nhật: 07/08/2026 — Asia/Ho_Chi_Minh
> Trạng thái: Giai đoạn 0–10 của Housekeeping và Phase 1–2 trung tâm vận hành phòng đã hoàn tất. Ngoài lịch Booking, readiness, phòng 360°, ownership đa chi nhánh và lifecycle Booking, hệ thống đã có yêu cầu khách dạng item, blocker chính thức, stop-sell theo khoảng thời gian và quy trình hai bước xác nhận mở lại phòng. Sales chỉ đọc trạng thái bán/blocker trong đúng chi nhánh; Booking bị chặn ở service khi stop-sell còn hiệu lực, kể cả đã qua ETA nhưng chưa được xác nhận mở lại. SQLite phát hiện 164 test: 159 pass và 5 PostgreSQL-only skip; 5/5 race test pass trên PostgreSQL thật. PostgreSQL đã áp dụng đến `accounts.0010`, `housekeeping.0014` và `room_operations.0001`; không tự quản lý tiến trình người dùng đang chạy tại cổng `8020`.

## 1. Mục đích tài liệu

Tài liệu này dùng để bàn giao công việc sang một tài khoản Codex khác.

Codex tiếp nhận phải đọc theo thứ tự:

1. `README.md` — nguồn yêu cầu nghiệp vụ duy nhất, gồm 1.610 dòng.
2. `PLAN.md` — kế hoạch, hiện trạng và quy tắc tiếp tục công việc.
3. Source hiện tại trong `/mnt/data/homestay/`.
4. Source tham chiếu chỉ đọc trong `/mnt/data/fasthub/`.

Không được tiếp tục code chỉ dựa trên phần Housekeeping MVP hiện có. Người dùng đã xác nhận phiên bản đó chưa sát với `README.md`.

## 2. Nguồn yêu cầu và nguồn tham chiếu

### Nguồn yêu cầu chính

- File: `/mnt/data/homestay/README.md`
- Phạm vi: quy trình vận hành Housekeeping hoàn chỉnh.
- Có 30 Acceptance Criteria: `AC-01` đến `AC-30`.
- Có 18 Test Case chính: `TC-01` đến `TC-18`.

Nếu code hoặc tài liệu khác mâu thuẫn với `README.md`, ưu tiên `README.md`.

### Dự án code tham chiếu

- Thư mục: `/mnt/data/fasthub/`
- Chỉ tham khảo, không sửa source Fasthub.
- Không sao chép database, bảng, role hoặc cấu hình môi trường của Fasthub vào Homestay.

Các phần Fasthub nên tham khảo:

- `common/access.py`: role guard và queryset scoping.
- `common/api_auth.py`: Bearer token authentication.
- `common/list_views.py`: filter state, pagination và list view convention.
- `accounts/models.py`: custom user, display name, access token và soft delete.
- `operations/models.py`: Ticket, WorkOrder, checklist snapshot và gallery ảnh.
- `operations/views.py`: API serialization, upload ảnh, checklist validation và transaction.
- `templates/base.html` cùng các template list/detail: layout backoffice.
- `technician_app/lib/src/services/api_client.dart`: Flutter API client.
- `technician_app/lib/src/services/field_service.dart`: service layer cho field app.
- `technician_app/lib/src/screens/technician_ticket_*`: danh sách/chi tiết công việc.
- `technician_app/lib/src/support/timestamped_image.dart`: xử lý ảnh, timestamp và vị trí.
- Các màn hình QR/GPS/camera trong `technician_app`.

Không được sao chép các điểm yếu sau của Fasthub:

- Lưu username/password trực tiếp trong `SharedPreferences`.
- Chưa có offline queue và local database mã hóa.
- Nhiều state transition chưa được kiểm soát bởi state machine tập trung.
- Thiếu optimistic version locking trong nhiều API.
- `operations/views.py` quá lớn; Homestay phải tách service/selectors/API serializers rõ ràng.
- Cấu hình database và secret riêng của Fasthub.

## 3. Yêu cầu người dùng đã chốt

- Bliss Home là hệ thống đa chi nhánh; mỗi chi nhánh có đúng một chủ tại một thời điểm.
- Chủ chi nhánh quản trị tài chính và vận hành độc lập trong chi nhánh mình, không có quyền xem chéo chi nhánh.
- Founder/quản trị nền tảng tạo chi nhánh và chỉ định/chuyển chủ; ownership phải là quan hệ theo chi nhánh, không dùng global role.
- Tất cả dữ liệu nghiệp vụ và tài chính mới phải có `branch_id`, được scope ở server và có test chống truy cập chéo chi nhánh.
- Database PostgreSQL dùng database `homestay`.
- Cấu hình database và secret được cố định riêng trong Django settings để không nhận nhầm biến môi trường của dự án khác trên server.
- Conda environment: `env`.
- Script khởi động: `startup.sh`.
- Code phải tham khảo convention của `/mnt/data/fasthub/`.
- Phải đọc yêu cầu và lập plan trước khi code.
- Không tự ý dừng hoặc thay thế dịch vụ của dự án khác.

## 4. Hiện trạng dự án Homestay

### Phần đã tồn tại trước Housekeeping

- Django project và custom `accounts.User`.
- Đăng nhập/đăng xuất.
- Luồng quên mật khẩu bằng OTP.
- PostgreSQL local và migration của `accounts`.
- Các tài khoản demo.

### Housekeeping MVP đã được tạo nhưng chưa đạt yêu cầu

Các file hiện có:

- `housekeeping/models.py`
- `housekeeping/services.py`
- `housekeeping/views.py`
- `housekeeping/urls.py`
- `housekeeping/admin.py`
- `housekeeping/migrations/0001_initial.py`
- `housekeeping/management/commands/seed_housekeeping_data.py`
- `housekeeping/tests.py`
- `templates/housekeeping/`

MVP hiện có một phần các luồng:

- Branch, membership, shift, room và task.
- Nhận việc, bắt đầu, checklist, pause/resume.
- Báo vật tư, báo sự cố.
- Hoàn thành và tạo QC task.
- QC approve/reject và rework cơ bản.
- API cùng HTML cơ bản.
- Một hàng đợi checklist offline rất đơn giản bằng `localStorage`.

Không được xem số test đang pass là bằng chứng đã hoàn thành README. Bộ test hiện tại chỉ bao phủ MVP, chưa bao phủ toàn bộ AC/TC.

### Database và seed đã chạy

Migration Housekeeping ban đầu đã từng được áp dụng vào PostgreSQL `homestay`.

Dữ liệu mẫu từng được tạo:

- 2 chi nhánh.
- 6 phòng.
- 6 task theo ngày seed.

Khi thiết kế lại model phải tạo migration tiến hóa dữ liệu; không được xóa database hoặc reset dữ liệu nếu chưa có chấp thuận rõ ràng.

### Tài khoản demo

Mật khẩu demo hiện tại: `Demo@2026Safe`

- `admin`
- `manager`
- `housekeeping`
- `housekeeping_lead`
- `qc`
- `technician`
- `warehouse`
- `customer_service`
- `viewer`
- `sales`

### Lưu ý cổng triển khai

- `app.yaml` của Homestay đang cấu hình cổng `8020`.
- Trước đó cổng này từng thuộc dịch vụ khác, vì vậy Codex không được tự dừng/ghi đè tiến trình tại cổng.
- Ngày 05/08/2026, người dùng xác nhận đã tự bật Homestay trên `8020`; kiểm tra HTTP trả `uvicorn`, trang `Đăng nhập | Bliss Home`, và đăng nhập `admin` thành công.
- Quyền hiện tại chỉ là truy cập/kiểm thử dịch vụ do người dùng bật. Không tự restart, stop hoặc thay đổi cách chạy cổng `8020` nếu chưa có yêu cầu mới.
- Browser audit sau khi sửa cho thấy các worker Uvicorn hiện tại vẫn phục vụ xen kẽ template/source cũ do được khởi động trước thay đổi. Cần người dùng restart dịch vụ rồi smoke test lại `8020`; Codex không tự thực hiện bước này.

## 5. Cách hiểu đúng phạm vi README

Đây không chỉ là màn hình CRUD task. Hệ thống gồm các khối nghiệp vụ sau:

1. Phân quyền theo role, chi nhánh, ca, khu vực, nhóm và quyền làm ngoài ca.
2. Danh sách task theo ngày/ca với tabs, filter, search và ưu tiên nghiệp vụ.
3. Nhận việc cạnh tranh an toàn giữa nhiều nhân viên.
4. Trả việc, bàn giao và phân công lại.
5. Xác minh phòng trước khi bắt đầu bằng cấu hình QR/GPS/Wi-Fi/camera.
6. Checklist có template, version và snapshot bất biến theo từng task.
7. Checklist đa loại dữ liệu, không chỉ checkbox.
8. Ảnh trước/sau, ảnh khu vực, ảnh sự cố, vật tư và QC.
9. Tiến độ, người cập nhật, thời điểm cập nhật và timeline gần thời gian thực.
10. Pause/resume cùng thời gian chờ riêng để tính SLA.
11. Supply request liên kết kho/chi nhánh và trạng thái xử lý.
12. Issue ticket liên kết task/phòng/booking/thiết bị và mức độ chặn phòng.
13. Completion summary và toàn bộ điều kiện chặn hoàn thành.
14. QC nhiều vòng và rework không ghi đè dữ liệu cũ.
15. SLA nhận việc/bắt đầu/hoàn thành/check-in risk và escalation.
16. Notification cho Housekeeping, Trưởng nhóm, Quản lý, QC, Kho và Kỹ thuật.
17. Activity Log đầy đủ.
18. Offline-first: cache task, checklist, ghi chú, ảnh, issue, sync và conflict.

## 6. Gap chính của MVP hiện tại

### 6.1. Data model

- `checklist_version` mới chỉ là chuỗi, chưa có template/version/definition/snapshot đúng nghĩa.
- Thiếu quan hệ booking thực, đang dùng `booking_code`.
- Thiếu assignment history và handover qua ca.
- Thiếu `assigned_by`, thông tin nhóm/kỹ năng và quyền theo khu vực đầy đủ.
- Thiếu SLA nhận việc, bắt đầu, hoàn thành, duration chuẩn và escalation state.
- Thiếu `last_progress_at`, `updated_by` và lịch sử tiến độ chi tiết.
- Thiếu `rework_started_at`, rework round và mapping checklist QC bị từ chối.
- Metadata ảnh chưa đầy đủ theo Task/Room/User/thời gian/sync/client ID.
- Notification/outbox chưa có.

### 6.2. Permission và state machine

- Chưa có role Trưởng nhóm Housekeeping đúng nghĩa.
- Chưa có đầy đủ thao tác tạo/giao/chuyển/hủy/đổi ưu tiên của Quản lý.
- Chưa có kiểm tra phòng đang được task khác xử lý đầy đủ.
- Xác minh QR mới chỉ kiểm tra có giá trị, chưa đối chiếu đúng phòng.
- Chưa lưu/kiểm tra đầy đủ GPS, Wi-Fi và xác nhận khách đồng ý vào phòng.
- Chưa có policy cấu hình cho làm ngoài ca, pause SLA và rework scope.

### 6.3. Checklist và completion

- Chưa hỗ trợ đầy đủ 9 loại checklist item trong UI/API.
- Chưa xử lý quy tắc item `FAILED` phải có ticket hoặc lý do được chấp nhận.
- Chưa chặn hoàn thành theo supply request chưa xử lý.
- Chưa có completion summary trước khi xác nhận.
- Luồng trạng thái cần ghi nhận rõ `COMPLETED` rồi `WAITING_QC` trong history.

### 6.4. Danh sách và chi tiết

- Chưa đủ tabs theo README.
- Chưa đủ filter khu vực, tầng, loại phòng, check-in risk, QC rework và assignee.
- Search chưa bao phủ khách theo permission.
- Chưa hiển thị đầy đủ thời gian còn lại, sắp quá hạn, sync state và ảnh bắt buộc.
- Detail thiếu booking/check-out/số khách/SLA/người giao/cảnh báo thiết bị.

### 6.5. SLA và notification

- Chưa có engine cảnh báo nhận/bắt đầu/hoàn thành.
- Chưa có escalation 5/15/30 phút.
- Chưa có notification cho các vai trò liên quan.
- Chưa có dashboard SLA và hiệu suất.

### 6.6. Offline

- `localStorage` hiện tại không đáp ứng yêu cầu mã hóa.
- Chưa cache danh sách task và thông tin phòng.
- Chưa lưu ảnh/blob offline.
- Chưa queue note, pause, issue và supply.
- Chưa có idempotency cho toàn bộ mutation.
- Chưa có giao diện xử lý `OFFLINE_SYNC_CONFLICT`.

### 6.7. Audit log

README yêu cầu tối thiểu các event:

- `TASK_VIEWED`
- `TASK_ACCEPTED`
- `TASK_REJECTED`
- `TASK_RETURNED`
- `TASK_STARTED`
- `TASK_PAUSED`
- `TASK_RESUMED`
- `TASK_PROGRESS_UPDATED`
- `CHECKLIST_ITEM_UPDATED`
- `PHOTO_ADDED`
- `SUPPLY_REQUEST_CREATED`
- `ISSUE_REPORTED`
- `TASK_COMPLETED`
- `TASK_SENT_TO_QC`
- `TASK_QC_REJECTED`
- `TASK_REWORK_STARTED`
- `TASK_CANCELLED`
- `TASK_REASSIGNED`

MVP chưa ghi đầy đủ và tên event hiện tại chưa hoàn toàn khớp README.

## 7. Kiến trúc đề xuất

### Backend Django

Giữ project Django hiện tại nhưng tổ chức lại Housekeeping:

```text
housekeeping/
├── api/
│   ├── auth.py
│   ├── errors.py
│   ├── serializers.py
│   ├── urls.py
│   └── views.py
├── services/
│   ├── assignments.py
│   ├── checklist.py
│   ├── issues.py
│   ├── notifications.py
│   ├── qc.py
│   ├── sla.py
│   ├── state_machine.py
│   ├── supplies.py
│   └── sync.py
├── selectors/
│   ├── permissions.py
│   └── tasks.py
├── management/commands/
├── migrations/
├── models.py hoặc models/
└── tests/
```

Không bắt buộc tách file đúng y hệt cấu trúc này nếu làm tăng rủi ro migration, nhưng phải tách nghiệp vụ khỏi view.

### Field app

Ưu tiên tham khảo `fasthub/technician_app` để xây ứng dụng Housekeeping mobile-first:

- Bearer token login.
- Navigation theo role.
- Task list/detail.
- Camera trực tiếp.
- Timestamp/GPS/QR.
- Secure storage cho token.
- Encrypted local database cho task và mutation queue.
- Background/automatic sync khi có mạng.

Nếu người dùng quyết định chỉ cần web/PWA thay vì Flutter, phải xác nhận trước khi triển khai giai đoạn offline.

### Backoffice

Tham khảo template Fasthub cho:

- Quản lý task.
- Điều phối/phân công.
- Checklist template/version.
- QC queue.
- Supply/issue queue.
- SLA dashboard.
- System Activity Log.

## 8. Kế hoạch triển khai chi tiết

### Giai đoạn 0 — Requirement traceability và gap audit

Trạng thái: **hoàn tất — chờ review**.

Công việc:

1. Tạo bảng ánh xạ từng requirement trong README tới model/service/API/UI/test.
2. Audit toàn bộ code Homestay hiện tại.
3. Audit pattern liên quan trong Fasthub.
4. Phân loại mỗi phần: giữ nguyên, refactor, thay mới hoặc bổ sung.
5. Liệt kê các điểm tùy chọn cần đưa vào configuration/policy.

Đầu ra bắt buộc:

- Gap report.
- State transition table.
- Permission matrix.
- Data model proposal.
- API contract checklist.
- Quyết định Flutter hay web/PWA cho offline.

Không sửa nghiệp vụ trước khi giai đoạn này được review.

Đầu ra ngày 05/08/2026:

- `docs/housekeeping/phase-0-audit.md`
- `docs/housekeeping/requirements-traceability.md`

### Giai đoạn 1 — Domain model và migration

Trạng thái: **hoàn tất — 05/08/2026**.

Đầu ra:

- Migration additive `housekeeping/migrations/0002_domain_foundation.py`.
- Data migration bảo toàn/backfill legacy `housekeeping/migrations/0003_backfill_domain_foundation.py`.
- Domain model, admin và seed đã được mở rộng.
- Migration/domain/seed tests; toàn bộ 37 test pass.
- Báo cáo `docs/housekeeping/phase-1-implementation.md`.

Thiết kế/bổ sung tối thiểu:

- Branch, area, team, membership, skill và shift assignment.
- Room, booking và room operational state.
- Housekeeping task.
- Task assignment/history/handover.
- Checklist template, version và item definition.
- Task checklist snapshot.
- Task media/attachment.
- Pause interval.
- Supply request và items.
- Issue ticket và attachment.
- QC round, QC failed item, QC media và rework round.
- SLA policy/state/escalation event.
- Notification/outbox/read receipt.
- Status history và activity log.
- Offline mutation/idempotency receipt nếu cần server-side.

Yêu cầu migration:

- Giữ dữ liệu hiện có.
- Có data migration cho trường cũ.
- Không reset database.
- Có constraint và index cho query chi nhánh/ca/status/due date.
- Có unique constraint cho idempotency key.

### Giai đoạn 2 — Permission, selectors và state machine

Trạng thái: **hoàn tất — 05/08/2026**.

Đầu ra:

- Policy quyền tập trung theo role/branch/area/team/shift trong `housekeeping/permissions.py`.
- Query scope và thứ tự ưu tiên nghiệp vụ trong `housekeeping/selectors.py`.
- State machine cùng đồng bộ trạng thái phòng trong `housekeeping/state_machine.py`.
- Idempotency receipt/replay trong `housekeeping/idempotency.py`.
- Service workflow được khóa transaction/version và mở rộng assign/reject/return/cancel/priority/QC.
- Test policy/state/idempotency và test cạnh tranh thật trên PostgreSQL.
- Báo cáo `docs/housekeeping/phase-2-implementation.md`.

Xây một nguồn sự thật duy nhất cho:

- Role và branch/area/team scope.
- Quyền xem và quyền thao tác.
- State transition task.
- Đồng bộ trạng thái phòng.
- Điều kiện nhận, bắt đầu, trả, pause, resume, complete và rework.
- Trưởng nhóm phân công/chuyển task.
- Quản lý tạo/hủy/đổi ưu tiên/xử lý ngoại lệ.
- QC approve/reject.

Concurrency:

- `transaction.atomic`.
- `select_for_update` cho accept/reassign/complete/QC.
- `version` cho optimistic locking.
- Chỉ một người nhận task thành công.
- Không cho hai active task cùng xử lý một phòng nếu policy không cho phép.
- Idempotency key cho mutation offline.

Bao phủ: `AC-01`, `AC-05`–`AC-11`, `AC-29`, `AC-30`; `TC-01`, `TC-03`–`TC-06`, `TC-17`.

### Giai đoạn 3 — API và query danh sách/chi tiết

Trạng thái: **hoàn tất — 05/08/2026**.

Đầu ra:

- API tách lớp tại `housekeeping/api/` gồm auth, error contract, query, serializer, URL và views.
- Bearer/session authentication; token login/refresh/logout và CSRF boundary.
- List/detail/completion-summary; filter, search, business ordering và stable pagination.
- Mutation API bắt buộc version + `Idempotency-Key` cho workflow/checklist/media/support/QC/management.
- Return/reject/reassign/handover/cancel/priority/rework/QC review endpoints.
- API/security/contract tests và báo cáo `docs/housekeeping/phase-3-implementation.md`.

Các contract phụ thuộc domain ở giai đoạn sau được giữ đúng phase: QC failed-item/media (GĐ5),
notification list/read (GĐ6), offline batch/conflict (GĐ8), support resolution queue đầy đủ (GĐ4/GĐ6).

Hoàn thiện contract README:

- `GET /api/v1/housekeeping/tasks`
- `POST /api/v1/housekeeping/tasks/{taskId}/accept`
- `POST /api/v1/housekeeping/tasks/{taskId}/start`
- `PATCH /api/v1/housekeeping/tasks/{taskId}/checklist-items/{itemId}`
- `POST /api/v1/housekeeping/tasks/{taskId}/pause`
- `POST /api/v1/housekeeping/tasks/{taskId}/resume`
- `POST /api/v1/housekeeping/tasks/{taskId}/supply-requests`
- `POST /api/v1/housekeeping/tasks/{taskId}/issues`
- `POST /api/v1/housekeeping/tasks/{taskId}/complete`

API bổ sung cần thiết cho UI đầy đủ:

- Task detail.
- Return/reject/handover/reassign.
- Upload/sync media.
- Resolve supply/issue.
- QC review và QC media.
- Notification list/read.
- Offline sync batch và conflict detail.

Danh sách phải hỗ trợ:

- Default ngày và ca hiện tại.
- Chi nhánh, khu vực, tầng, loại phòng.
- Task type, status, priority, assignee.
- Overdue, check-in risk và QC rework.
- Search theo dữ liệu được phép.
- Thứ tự QC rework → check-in gần → overdue → urgent → assigned → due time.
- Pagination ổn định.

Mã lỗi phải khớp mục 28 trong README.

Bao phủ: `AC-01`–`AC-09`, `AC-26`, `AC-29`; `TC-01`–`TC-05`, `TC-17`, `TC-18`.

### Giai đoạn 4 — Luồng thực hiện task

Trạng thái: **hoàn tất backend — 05/08/2026**.

Đầu ra:

- Validation và normalization đủ 9 loại checklist, item version và failed-item exception approval.
- Xác minh phòng kết hợp QR/GPS/Wi-Fi/camera, guest consent và room row lock.
- Media checksum/source/captured time/GPS/metadata/link issue-supply; direct-camera evidence policy.
- Pause reason, support state, thời lượng và SLA excluded seconds.
- Supply/issue queue theo role/branch, optimistic version và resolution flow.
- Completion summary/validator dùng chung cho checklist/ảnh/failed/support/pending sync.
- Migration additive `0004_execution_verification_policy.py` và báo cáo `docs/housekeeping/phase-4-implementation.md`.

Xây đầy đủ:

- Nhận và trả task với lý do.
- Bàn giao qua ca.
- Xác minh phòng.
- Cảnh báo khách trong phòng và xác nhận đồng ý.
- Checklist đa kiểu dữ liệu.
- Tính tiến độ tự động.
- `last_progress_at`, `updated_by` và timeline.
- Camera/ảnh trước/sau/khu vực.
- Pause/resume và thời lượng pause.
- Supply request.
- Issue ticket và blocking rule.
- Completion summary.
- Validation checklist/ảnh/failed item/supply/issue/sync trước complete.

Bao phủ: `AC-09`–`AC-20`, `AC-25`, `AC-26`; `TC-03`, `TC-06`–`TC-12`.

### Giai đoạn 5 — QC và rework

Trạng thái: **hoàn tất backend/API — 05/08/2026**.

Đầu ra:

- QC media upload theo đúng pending round và QC permission.
- Reject payload gồm failed items, reason/note, deadline, media và immutable result snapshot.
- `QCFailedItem` + `ReworkRound` lifecycle PENDING/IN_PROGRESS/SENT_TO_QC/COMPLETED.
- Branch policy giới hạn rework chỉ failed items; API chặn sửa item ngoài scope.
- Mỗi lần gửi lại tạo QC round/checklist snapshot mới, không ghi đè vòng cũ.
- Room state `REWORK_REQUIRED`/`CLEANING`/`WAITING_QC`/`READY` qua state machine.
- Báo cáo `docs/housekeeping/phase-5-implementation.md`.

Xây đầy đủ:

- Tạo QC task khi Housekeeping hoàn thành.
- Notification cho QC.
- QC checklist và QC media.
- Reject reason, failed item, note và deadline làm lại.
- Phòng chuyển `REWORK_REQUIRED`.
- Housekeeping thấy rõ nội dung phải làm lại.
- Tăng rework count và ghi `rework_started_at`.
- Lưu riêng từng QC/rework round.
- Gửi QC lần sau mà không ghi đè vòng cũ.
- Chỉ chuyển phòng `READY` sau QC approve hoặc policy không cần QC.

Bao phủ: `AC-21`–`AC-25`; `TC-13`–`TC-15`.

### Giai đoạn 6 — SLA, notification và dashboard

Trạng thái: **hoàn tất backend/API — 05/08/2026**.

Đã triển khai:

- SLA policy snapshot/state cho acceptance/start/completion/standard duration và pause excluded time.
- Evaluator gọi định kỳ bằng management command; near-due, breach và check-in risk.
- Escalation 5/15/30 phút đúng Quản gia/Trưởng nhóm/Quản lý, có unique event + outbox dedupe.
- Check-in risk tự nâng task lên `URGENT`, ghi activity và cảnh báo assignee/lead/manager.
- Notification nghiệp vụ cho Housekeeping, lead, manager, QC, Kho và Kỹ thuật; API list/read idempotent.
- Dashboard SLA và hiệu suất theo nhân viên/ca/chi nhánh với active/pause/rework metrics.
- Dedicated test `test_phase6_sla_notifications.py`.
- Báo cáo `docs/housekeeping/phase-6-implementation.md`.

SLA:

- Acceptance deadline.
- Start deadline.
- Completion deadline.
- Standard duration.
- Next check-in risk.
- Pause inclusion/exclusion theo policy.

Escalation:

- Trễ 5 phút: Quản gia.
- Trễ 15 phút: Trưởng nhóm.
- Trễ 30 phút: Quản lý.
- Có nguy cơ ảnh hưởng check-in: ưu tiên khẩn cấp.

Notification cho:

- Housekeeping.
- Trưởng nhóm.
- Quản lý.
- QC.
- Kho.
- Kỹ thuật.

Dashboard:

- Tiến độ gần thời gian thực.
- Task gần/quá SLA.
- Phòng có nguy cơ không kịp check-in.
- Thời gian active/pause.
- Số vòng rework.
- Hiệu suất theo nhân viên/ca/chi nhánh.

Bao phủ: `AC-04`, `AC-18`, `AC-20`, `AC-26`; `TC-10`, `TC-13`, `TC-18`.

### Giai đoạn 7 — Offline-first

Trạng thái: **hoàn tất backend + Flutter MVP — 05/08/2026**.

Đã triển khai:

- Flutter field app trong `housekeeping_app/`, có Android/iOS project và cấu hình bảo mật platform.
- Token trong secure storage; cache task/detail, queue, conflict và photo BLOB trong SQLCipher.
- Queue checklist, note, photo, issue, supply, pause/resume và complete với client UUID, idempotency key, base version và dependency.
- Sync batch tối đa 100 phần tử, topological order, result/receipt riêng và không rollback mutation độc lập.
- Exact version conflict giữ base/local/server snapshot; không tự ghi đè hoặc auto-rebase.
- Màn hình sync hiển thị pending/failed/conflict, cho retry/discard rõ ràng; complete bị chặn khi còn dữ liệu unresolved.
- Web đã loại bỏ business queue dùng `localStorage`.
- Dedicated backend test `test_phase7_offline_sync.py` và Flutter dependency planner tests.
- Báo cáo `docs/housekeeping/phase-7-implementation.md`.

Không dùng `localStorage` cho dữ liệu nghiệp vụ nhạy cảm.

Yêu cầu:

- Secure storage cho access token.
- Encrypted local database.
- Cache task list, detail và thông tin phòng.
- Queue checklist/note/photo/issue/supply/pause mutation.
- Lưu photo blob/path và metadata offline.
- Client-generated UUID/idempotency key.
- Hiển thị `synced`, `pending`, `failed`, `conflict`.
- Tự sync theo đúng thứ tự dependency.
- Không tạo dữ liệu trùng.
- Gặp version conflict không được tự ghi đè.
- Có màn hình xem server/local changes và retry/resolve.
- Không complete cuối nếu dữ liệu bắt buộc còn pending.

Bao phủ: `AC-27`–`AC-29`; `TC-16`, `TC-17`.

### Giai đoạn 8 — UI/UX hoàn chỉnh

Trạng thái: **hoàn tất Flutter/backoffice MVP — 05/08/2026**.

Đã triển khai:

- Flutter có đủ 7 tab, search và filter ngày/chi nhánh/khu vực/ca/tầng/loại phòng/task/trạng thái/ưu tiên/assignee/overdue/check-in risk/QC rework.
- Task card hiển thị phòng/chi nhánh/assignee/SLA countdown/check-in/cảnh báo/checklist/ảnh/sync state; mọi cảnh báo đều có chữ + icon, không chỉ dùng màu.
- Detail chia section thông tin task, phòng/booking, SLA, QC/rework, checklist, gallery, support, note và timeline.
- Typed editor đủ 9 loại checklist; failed item bắt buộc lý do; photo item nối dependency ảnh → checklist.
- Camera/gallery giữ ảnh mã hóa, hiển thị preview và trạng thái pending/failed/conflict.
- Completion summary gọi chung backend blocker, hiển thị duration/checklist/ảnh/vật tư/sự cố và chặn khi local unresolved.
- Conflict UI so sánh base/local/server trước khi discard/retry; failed sync có retry/discard.
- Cache tab/filter riêng, tự drain chuỗi checklist → photo → complete trong một reconnect; cache được bind theo user để không lộ dữ liệu trên thiết bị dùng chung.
- Backoffice có dashboard điều phối/SLA/hiệu suất, team progress, QC queue, Kho/Kỹ thuật queue, Activity Log và Notification Center theo scope.
- Backoffice task list/detail có filter mở rộng, điều chuyển, đổi ưu tiên, hủy task và QC failed-item/deadline form.
- Dedicated test `test_phase8_ui.py`, Flutter presentation/unit/widget tests và báo cáo `docs/housekeeping/phase-8-implementation.md`.

Field app/mobile UI:

- Tabs theo README.
- Filter/search đầy đủ.
- Task card đủ thông tin mục 8.3.
- Cảnh báo không chỉ dựa vào màu.
- Countdown/overdue/check-in risk.
- Task detail theo mục 15.
- Checklist theo nhóm và type.
- Camera, gallery và sync status.
- Timeline.
- Completion summary.
- QC rework screen.
- Accessibility và thao tác thuận tiện trên màn hình nhỏ.

Backoffice UI:

- Điều phối và quản lý task.
- Team progress.
- QC queue.
- Supply/issue queue.
- SLA dashboard.
- Activity log.

### Giai đoạn 9 — Test, migration và triển khai

Trạng thái: **hoàn tất test/migration và deploy readiness — 05/08/2026; chưa production deploy**.

Đã triển khai và kiểm chứng:

- Đóng `AC-26` bằng polling tiến độ 30 giây trên Flutter và task list/dashboard backoffice; chỉ poll khi online/visible và không reload khi form có dữ liệu chưa gửi.
- Bổ sung integration test cho progress metadata và migration test bảo toàn receipt offline qua `0005`.
- Bổ sung PostgreSQL row-lock race test: hai task cùng bắt đầu một phòng chỉ một task thành công.
- Regression đăng nhập/token/quên mật khẩu pass.
- Toàn bộ Django suite sau UI hardening/focus fix: 100 test, 98 pass và 2 PostgreSQL-only skip trên SQLite; hai test bị skip chạy riêng PostgreSQL đạt 2/2.
- Flutter analyze pass, 0 issue; Flutter unit/widget đạt 9/9. Không chạy Android build theo yêu cầu người dùng.
- Regression tiếp nối trên Flutter 3.41.9 phát hiện và sửa giá trị semantics của progress bar: giữ nhãn đọc màn hình có đơn vị ở task card nhưng truyền giá trị số hợp lệ cho progress semantics; test widget đã khóa trường hợp 70% và suite vẫn đạt 9/9.
- Browser audit đăng nhập thật bằng `admin` trên Chrome desktop/mobile đã sửa: menu mobile bị cắt, 2 tab web còn thiếu, lọc ca/ngày mặc định, nhãn form/accessibility, timestamp UTC và mã trạng thái thô trên dashboard, favicon 404 và bước xác nhận cho thao tác phá hủy. Sau sửa không còn horizontal overflow toàn trang, control thiếu nhãn hoặc browser console error; tab support/waiting-QC/done có regression test.
- Focus navigation được khóa đúng trên `#nav-panel`: mở menu chuyển focus vào mục `aria-current`, Escape đóng menu và trả focus về toggle; mục active được giữ theo route và có focus-visible/selected state rõ ràng.
- Đã backup PostgreSQL trước migration tại `/tmp/homestay-pre-phase9-20260805.dump`, áp dụng `housekeeping.0002`–`0005`, rồi smoke test schema/data.
- PostgreSQL giữ nguyên 8 user, 2 chi nhánh, 6 phòng, 6 task; backfill tạo 6 SLA state và 2 branch policy.
- `makemigrations --check --dry-run`, Django system check và `startup.sh` syntax đều pass.
- Trong lần kiểm chứng Phase 9 ban đầu, Codex không khởi động/deploy ứng dụng và không chiếm cổng `8020`; dịch vụ hiện tại do người dùng tự bật sau đó.
- Báo cáo: `docs/housekeeping/phase-9-implementation.md`.

Phần chủ động hoãn/chờ quyết định:

- Android build và physical-device E2E được hoãn theo yêu cầu người dùng ngày 05/08/2026.
- Production deploy cần xác nhận quyền sở hữu/cách vận hành dịch vụ hiện tại ở `8020`, domain/TLS và production settings; `check --deploy` hiện báo 5 cảnh báo bảo mật do đang dùng local-development settings.

### Giai đoạn 10 — Đóng gap sau audit lại PLAN

Trạng thái: **hoàn tất code/test/migration — 06/08/2026; chờ restart runtime do người dùng quản lý**.

Đã triển khai:

- API/backoffice tạo task idempotent, snapshot checklist, assignment, SLA, room state và notification.
- Migration `0006` cho skill bắt buộc trên task; selector/accept/reassign enforce đủ skill.
- Audit `TASK_VIEWED`, manager note và notification trên web/mobile.
- SLA evaluator chạy định kỳ trong `startup.sh`.
- Flutter dùng scanner QR, GPS và Wi-Fi thiết bị thật; bổ sung filter còn thiếu, Notification Center và QC media.
- Offline camera verification giải quyết client media ID sang server photo ID, đồng thời lưu receipt dependency phía backend.
- Báo cáo: `docs/housekeeping/phase-10-gap-closure.md`.

Bộ test bắt buộc:

- Unit test cho state machine và policy.
- Permission test theo role/branch/shift/area.
- API contract test.
- PostgreSQL concurrency test thật cho hai người nhận cùng task.
- Integration test task → room → QC → rework.
- Idempotency và conflict test.
- Flutter widget test hoặc PWA UI test.
- E2E offline checklist/photo/issue/sync.
- Regression test cho login và quên mật khẩu.

Definition of Done:

- `AC-01`–`AC-30` đều có code và test dẫn chiếu.
- `TC-01`–`TC-18` đều pass.
- Django system check pass.
- Không có migration chưa tạo.
- Test pass trên môi trường test.
- Smoke test PostgreSQL pass.
- Không làm mất dữ liệu hiện có.
- Không chiếm cổng của dự án khác.

## 9. Ma trận AC/TC cấp cao

| Nhóm | Acceptance Criteria | Test Case |
|---|---|---|
| Scope, ca, filter | AC-01–AC-04, AC-07–AC-08 | TC-01, TC-02, TC-05, TC-18 |
| Accept/concurrency | AC-05–AC-09, AC-29–AC-30 | TC-03, TC-04, TC-17 |
| Start/progress | AC-10–AC-13, AC-25–AC-26 | TC-06, TC-07 |
| Completion validation | AC-14–AC-16 | TC-08, TC-09, TC-11 |
| Supply/issue/pause | AC-17–AC-20 | TC-10, TC-11, TC-12 |
| QC/rework | AC-21–AC-24 | TC-13, TC-14, TC-15 |
| Offline/sync | AC-27–AC-29 | TC-16, TC-17 |

Ma trận chi tiết từng requirement phải được tạo trong giai đoạn 0; bảng này chỉ dùng để định tuyến công việc.

## 10. Quy tắc làm việc cho Codex tiếp nhận

1. Không sửa `/mnt/data/fasthub/`.
2. Không xóa hoặc reset PostgreSQL.
3. Không coi MVP hiện tại là kiến trúc bắt buộc phải giữ.
4. Trước mỗi phase, đọc lại phần README tương ứng.
5. Mỗi thay đổi nghiệp vụ phải có test liên kết AC/TC.
6. Không thêm trạng thái hoặc rule trái README nếu chưa giải thích rõ.
7. Các yêu cầu có từ “có thể”, “nếu cấu hình” phải đưa vào policy/configuration, không hard-code một hành vi duy nhất nếu chưa chốt.
8. Dùng transaction, row lock, version và idempotency ở backend; không dựa vào UI.
9. Không lưu password người dùng trong mobile local storage.
10. Không tự start/stop/restart hoặc thay thế tiến trình ở `8020`; người dùng đã tự bật Homestay và chỉ cho phép Codex truy cập kiểm thử.
11. Bảo tồn thay đổi và dữ liệu hiện có của người dùng.
12. Báo tiến độ bằng kết quả kiểm chứng, không chỉ liệt kê file đã tạo.

## 11. Việc Codex mới cần làm ngay

Phạm vi MVP Housekeeping không còn hạng mục bắt buộc. Trong roadmap vận hành phòng,
ownership, tạo Booking, lifecycle reschedule/cancel và yêu cầu đặc biệt có cấu trúc đã
hoàn tất; migrations production đã áp dụng đến `housekeeping.0014`. Việc code tiếp theo
là triển khai blocker/stop-sell theo khoảng ngày và quy trình xác nhận mở lại. `HCM` hiện
vẫn thuộc tài khoản `manager`; cần người dùng xác nhận có chuyển sang tài khoản chủ riêng
hay đây là ownership mong muốn. Việc vận hành còn lại là người dùng restart worker `8020`
để nạp source mới rồi browser smoke test; Codex không tự restart/stop tiến trình này.
Dịch vụ vẫn dùng cấu hình development, nên trước production phải chốt domain/TLS và tách
security settings. Android build/device E2E vẫn hoãn theo yêu cầu cũ.
