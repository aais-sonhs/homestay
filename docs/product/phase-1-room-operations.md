# Giai đoạn 1 — Trung tâm vận hành phòng

> Bắt đầu triển khai: 07/08/2026.
> Trạng thái: Phase 1 và Phase 2 đã hoàn thành: read models, ownership, lifecycle
> Booking bởi Sales, yêu cầu khách có cấu trúc, blocker chính thức và stop-sell có
> xác nhận mở lại. Production đã áp dụng đến `housekeeping.0014` và
> `room_operations.0001`.

## Đã triển khai

### Quản lý chi nhánh trong backoffice

- Chỉ Super Admin có hai menu ngoài sidebar `Chi nhánh` và `Chủ chi nhánh`; không cần dùng Django Admin.
- Có danh sách, tìm kiếm, lọc trạng thái, thêm và chỉnh sửa chi nhánh.
- Có danh sách, tìm kiếm, tạo và chỉnh sửa tài khoản chủ chi nhánh.
- Tại danh sách chủ chi nhánh có nút `Phân quyền`; Super Admin chọn trực tiếp một
  hoặc nhiều chi nhánh cần gán/chuyển ngay trong hồ sơ chủ, không phải dò sang màn
  hình sửa từng chi nhánh.
- Chi nhánh mới bắt buộc chọn một chủ; hệ thống tự cấp membership quản lý tại đúng chi nhánh đó.
- Khi chuyển chủ, membership do ownership của chủ cũ bị vô hiệu hóa và chủ mới được cấp quyền tại chi nhánh.
- Ngừng hoạt động là soft state, không xóa dữ liệu; bị chặn khi còn task hoặc booking mở.
- Chi nhánh mới tự có Housekeeping policy, kho mặc định và SLA mặc định.
- Mỗi lần tạo/chuyển chủ có bản ghi audit chỉ đọc và hiển thị tại màn hình sửa chi nhánh.

### Hoàn thiện ownership và dữ liệu cũ

- Migration `housekeeping.0011` gán chủ cho chi nhánh cũ khi và chỉ khi chi nhánh có
  đúng một membership `MANAGER` đang hoạt động; trường hợp mơ hồ sẽ dừng migration
  với thông báo rõ ràng thay vì tự đoán.
- Sau backfill, `Branch.owner` là khóa ngoại bắt buộc ở tầng database.
- Ownership PostgreSQL sau migration: `DALAT` thuộc `admin.dalat`; `HCM` vẫn thuộc
  `manager`. Cả hai owner đều có membership Manager đang hoạt động; cần xác nhận riêng
  nếu `manager` của HCM chỉ là dữ liệu demo.
- Quyền chủ chi nhánh được kiểm tra từ quan hệ `Branch.owner`; giá trị role
  `branch_owner` một mình không cấp quyền ở chi nhánh khác.
- Tên/số điện thoại khách được kiểm tra theo từng chi nhánh, tránh lộ dữ liệu khi một
  chủ có thêm membership chỉ xem ở nơi khác.

### App `room_operations`

App này chứa read-model xuyên domain và sở hữu blocker/stop-sell chính thức.

- `selectors.py`: tổng hợp Booking, Room, HousekeepingTask, IssueTicket và TaskPhoto.
- `views.py`: scope dữ liệu theo chi nhánh và ẩn thông tin khách với vai trò hiện trường.
- `urls.py`: lịch vận hành, readiness board và hồ sơ phòng.

### Blocker và stop-sell — `/operations/stop-sell/`

- Sự cố chặn readiness tạo `RoomBlocker` chính thức cùng transaction; migration
  `room_operations.0001` backfill các `IssueTicket` chặn phòng còn mở.
- Blocker có trạng thái `ACTIVE`, `CLEARANCE_PENDING`, `CLEARED` hoặc `CANCELLED`;
  đóng sự cố chỉ gửi yêu cầu gỡ chặn, không tự đánh dấu phòng sẵn sàng.
- Manager, chủ chi nhánh và Founder tạo stop-sell theo phòng, thời điểm bắt đầu, ETA
  dự kiến mở lại, lý do và nguồn blocker; mọi quan hệ đều được kiểm tra cùng chi nhánh.
- ETA không tự kết thúc dừng bán. Phòng chỉ mở lại sau hai bước yêu cầu và xác nhận;
  stale version bị từ chối, blocker nguồn được gỡ cùng transaction khi xác nhận.
- Stop-sell tương lai có thể hủy trước thời điểm bắt đầu. Một phòng không thể có hai
  stop-sell đang mở/lên lịch; cạnh tranh được tuần tự hóa bằng row lock.
- Tạo/đổi lịch Booking bị chặn ở service nếu giao với stop-sell; booking đã bị ảnh
  hưởng vẫn sửa được thông tin khách nhưng không được đổi phòng hoặc thời gian.
- Readiness, lịch vận hành và hồ sơ phòng 360° hiển thị blocker, stop-sell và trạng
  thái bán tập trung. Sales xem được trong đúng chi nhánh nhưng không có quyền mutation.
- Mỗi chuyển trạng thái có history snapshot bất biến và Outbox event cho readiness,
  blocker và vòng đời stop-sell.

### App `reservations` — `/bookings/`

- Nhân viên Kinh doanh tạo booking hộ khách tại đúng chi nhánh có membership `SALES`.
- Chủ chi nhánh, Manager và Founder cũng tạo được booking trong phạm vi quản lý.
- Form bắt buộc tên/SĐT khách, phòng, thời gian nhận/trả và kiểm tra phòng bị khóa,
  ngừng phục vụ, sai chi nhánh hoặc trùng khoảng thời gian.
- Mã booking có thể nhập hoặc để hệ thống tự sinh; nguồn và người tạo được lưu để audit.
- Khi tạo thành công, hệ thống idempotently sinh hai công việc có checklist snapshot,
  SLA state, status history, activity log và outbox event:
  - Chuẩn bị phòng: bắt đầu trước check-in 90 phút, hạn trước check-in 30 phút.
  - Dọn sau trả phòng: bắt đầu lúc check-out, hạn sau đó 60 phút.
- Task tương lai không đổi trạng thái phòng sang chờ dọn ngay lúc booking được tạo.
- Checkout task của booking trước được cập nhật `next_checkin_at` khi có booking kế tiếp,
  phục vụ cảnh báo SLA sát giờ nhận phòng.
- Sales, chủ chi nhánh, Manager và Founder có thể sửa booking `BOOKED` trong đúng phạm vi:
  đổi phòng, check-in/check-out, thông tin khách và yêu cầu đặc biệt.
- Đổi lịch/phòng cập nhật cùng transaction cho hai task chưa bắt đầu: phòng/khu vực,
  lịch thực hiện, deadline nhận/bắt đầu/hoàn thành, standard duration, `next_checkin_at`,
  yêu cầu khách và `TaskSLAState`. Task đã bắt đầu/hoàn tất/hủy sẽ chặn thay đổi booking.
- Hủy booking bắt buộc nhập lý do và hủy hai task qua state machine, kết thúc assignment,
  thông báo người liên quan và tính lại `next_checkin_at` của booking liền trước.
- Booking có optimistic `version`, người cập nhật/hủy, lý do/thời điểm hủy và
  `BookingChangeLog` snapshot bất biến; event `BOOKING_CHANGED`/`BOOKING_CANCELLED` cùng
  event task tương ứng được ghi qua outbox. Gửi lại thao tác hủy không tạo dữ liệu trùng.
- Danh sách booking, form tạo/sửa/hủy và nút tạo nhanh đã được nối vào sidebar/Lịch vận hành.

### Yêu cầu đặc biệt có cấu trúc

- Mỗi yêu cầu là một `BookingSpecialRequest` gắn trực tiếp cả `booking_id` và
  `branch_id`, có loại, thời điểm áp dụng, mức ưu tiên, nội dung, số lượng và thứ tự.
- Form booking cho phép thêm/xóa tối đa 20 dòng; dữ liệu POST kiểu cũ vẫn được nhận và
  chuẩn hóa thành item `OTHER/ALL` để không làm gãy client cũ.
- Trường text `Booking.special_requests` và `HousekeepingTask.special_request` được giữ
  làm bản tóm tắt tương thích, không còn là nguồn dữ liệu chính.
- Task tự động nhận snapshot JSON theo đúng pha: chuẩn bị check-in nhận item
  `CHECKIN/STAY/ALL`, còn dọn sau checkout nhận `CHECKOUT/ALL`.
- Snapshot item được đưa vào API task, audit booking, event tạo/đổi booking và event
  tạo/reschedule task; thay đổi request dùng chung optimistic version và transaction
  với lifecycle task.
- Migration `0014` bảo toàn text cũ, tạo item theo đúng chi nhánh và backfill snapshot
  cho cả task gắn booking lẫn task legacy độc lập.

### Lịch vận hành — `/operations/schedule/`

- Lọc theo ngày và chi nhánh.
- Hiển thị check-in/check-out, yêu cầu đặc biệt và task liên quan.
- Cảnh báo booking trả phòng thiếu lịch dọn.
- Cảnh báo booking nhận phòng khi phòng/task/blocker chưa đạt.
- Hiển thị công việc vận hành không gắn booking.

### Trạng thái phòng — `/operations/rooms/`

- Lọc theo từ khóa, chi nhánh và readiness state.
- Tính bốn trạng thái: `READY`, `OCCUPIED`, `NOT_READY`, `BLOCKED`.
- Blocker hiện tại gồm: phòng khóa, out-of-service, sự cố chặn, trạng thái vệ sinh
  chưa đạt và task gần thời điểm thực hiện còn mở.
- Rủi ro check-in chỉ tính cho booking trong 24 giờ tới.
- Hiển thị task mở, booking tiếp theo và thời gian dự kiến hoàn tất.

### Hồ sơ phòng 360° — `/operations/rooms/<room_id>/`

- Readiness và blocker.
- Booking gần nhất.
- Công việc theo phòng.
- Sự cố và trạng thái xử lý.
- Gallery ảnh lấy từ các task của phòng.
- Timeline tổng hợp booking, task, issue và ảnh.

### Giao diện backoffice theo Fasthub

- Dùng chung nền `#f4f7fe`, font Inter, panel trắng bo 20px, khoảng cách rộng và
  shadow/transition cùng ngôn ngữ thiết kế với Fasthub.
- KPI tại Điều phối, Lịch vận hành và Trạng thái phòng là card gradient 150px có
  icon, màu ngữ nghĩa, nhãn capsule, số liệu lớn và ghi chú ngắn.
- Danh sách Booking, stop-sell và trạng thái task dùng badge có chấm màu; bảng dữ
  liệu, form, nút và heading được chuẩn hóa bằng CSS dùng chung.
- Card readiness, stop-sell, hàng đợi Kho/Kỹ thuật và Thông báo có nền trạng thái,
  accent màu và bố cục responsive riêng cho desktop/mobile.

## Quyền và bảo mật dữ liệu

- Founder xem toàn bộ chi nhánh.
- Mỗi chi nhánh mới có đúng một chủ sở hữu; chủ chỉ xem và quản trị chi nhánh mình sở hữu.
- Trường owner là bắt buộc ở tầng database sau migration backfill có kiểm soát.
- Người dùng khác chỉ xem phòng/booking thuộc BranchMembership đang hoạt động.
- Sales/CSKH/Manager/Founder và chủ đúng chi nhánh xem tên khách.
- Housekeeping vẫn xem yêu cầu phục vụ nhưng không thấy tên khách trên lịch vận hành.
- Sales chỉ đọc trạng thái task dọn của chi nhánh, không được nhận/thực hiện/điều phối task.
- Quyền sửa/hủy booking dùng lại scope tạo booking ở server; Housekeeping trong cùng chi
  nhánh nhận 403, còn tài khoản ngoài chi nhánh nhận 404 để không lộ sự tồn tại bản ghi.
- Truy cập hồ sơ phòng ngoài scope trả về 404.

## Kiểm thử

- Test schedule kết hợp booking/task/yêu cầu/risk.
- Test readiness và blocker.
- Test phòng 360° tổng hợp dữ liệu.
- Test scope chi nhánh và ẩn tên khách.
- Test Founder xem đa chi nhánh.
- Regression UI/account hiện có vẫn pass.
- Regression khóa việc chủ chi nhánh quản lý hoặc đọc tên khách chéo chi nhánh.
- Test Sales tạo booking, chặn trùng phòng, chặn chi nhánh ngoài quyền, sinh task đúng
  thời điểm, idempotency, checklist/SLA/audit/outbox và không tạo check-in risk giả từ
  checkout task tương lai.
- Test reschedule/cancel bao phủ đồng bộ task/SLA, rollback khi task đã bắt đầu, stale
  version, cross-branch, audit/outbox, idempotency, quyền web và migration bảo toàn dữ liệu.
- Toàn bộ Django suite trên SQLite: 166 test được phát hiện, 160 pass và 6 test
  PostgreSQL-only skip.
- PostgreSQL thật: 6/6 row-lock/race test pass, gồm hai reschedule cùng booking chỉ một
  thao tác thành công và hai stop-sell cạnh tranh chỉ một bản ghi được tạo; lỗi
  `FOR UPDATE` trên nullable join đã được khóa bằng `of=("self",)`, kể cả toàn bộ
  chuỗi tạo stop-sell → yêu cầu mở lại → xác nhận mở lại khi blocker không có issue.
- `makemigrations --check --dry-run`, Django system check, `git diff --check` và
  `startup.sh` syntax đều pass.

## Migration PostgreSQL ngày 07/08/2026

- Backup trước Sales/booking automation:
  `/tmp/homestay-pre-sales-booking-20260807-095033.dump`.
- Backup sát trước booking lifecycle:
  `/tmp/homestay-pre-booking-lifecycle-20260807-100513.dump`.
- Đã áp dụng `accounts.0010`, `housekeeping.0012` và `housekeeping.0013` thành công.
- Smoke check sau migration giữ 2 chi nhánh, 18 booking và 18 task; booking cũ được
  backfill `version=1`, không tự dựng lịch sử giả cho dữ liệu legacy.
- Không restart, stop hoặc thay thế worker đang chạy tại cổng `8020`.
- Backup trước structured request:
  `/tmp/homestay-pre-structured-requests-20260807-103510.dump` (đã kiểm tra bằng
  `pg_restore -l`).
- Đã áp dụng `housekeeping.0014` thành công; smoke check giữ 18 booking và 18 task,
  backfill 9 item, không có `branch_id` sai booking, booking text thiếu item hoặc task
  text thiếu snapshot.
- Cấu hình PostgreSQL race test đã đổi khỏi host localhost cũ sang đúng DB host dự án;
  6/6 race/regression test pass trên database tách biệt `test_homestay` và database test đã được xóa.
- Backup trước blocker/stop-sell:
  `/tmp/homestay-pre-stop-sell-20260807-110826.dump` (đã kiểm tra bằng `pg_restore -l`).
- Đã áp dụng `room_operations.0001` thành công; smoke check giữ 18 booking và 18 task,
  không có quan hệ branch–room sai hoặc sự cố chặn đang mở bị thiếu blocker. Production
  hiện chưa có blocker hay stop-sell nên migration không tự tạo dữ liệu giả.
- Backup trước dữ liệu demo:
  `/tmp/homestay-pre-demo-seed-20260807-114103.dump` (đã kiểm tra bằng `pg_restore -l`).
- Command `seed_operations_demo_data` đã tạo 11 phòng tình huống, 6 booking, 14 task,
  10 yêu cầu khách, 2 sự cố, 4 ảnh, 6 blocker và 5 stop-sell trên PostgreSQL. Hậu kiểm
  không có mismatch branch/room hoặc phòng có nhiều stop-sell mở; 10/10 tài khoản demo
  đăng nhập được bằng mật khẩu chuẩn.
- Hướng dẫn scenario và chạy lại idempotent: `docs/product/demo-data.md`.

## Việc tiếp theo đã chốt

1. Xác nhận owner của `HCM`; chuyển sang tài khoản chủ riêng nếu `manager` chỉ là demo.
2. Restart các worker do người dùng quản lý rồi smoke test giao diện mới tại cổng `8020`.
3. Triển khai `MaintenanceWorkOrder`, `Asset` và quy trình thợ hoàn thành → vận hành xác nhận.
4. Sau đó thêm bảo trì phòng ngừa và liên kết vật tư/chi phí sửa chữa.
5. Khi module tài chính được tạo, bổ sung cùng chuẩn regression đọc/sửa/export/tổng
   hợp chéo chi nhánh; hiện chưa có bảng hoặc endpoint tài chính để kiểm thử.
