# Nền tảng vận hành Homestay — yêu cầu tổng thể và roadmap

> Ghi nhận ngày 07/08/2026.
> Tài liệu này mở rộng phạm vi sản phẩm từ Housekeeping sang trung tâm vận hành phòng.
> Yêu cầu chi tiết của quy trình Housekeeping trong `README.md` vẫn giữ nguyên hiệu lực.
> Nhật ký triển khai Giai đoạn 1: `docs/product/phase-1-room-operations.md`.

## 1. Bối cảnh hiện tại

Quy trình vận hành đang phụ thuộc vào Zalo, sheet và trí nhớ của từng nhân sự:

1. CSKH tổng hợp lịch booking, gửi lịch dọn qua Zalo; quản gia gửi ảnh vào nhóm sau khi dọn.
2. Quản gia tự ghi nhớ khu vực và hạng mục; CSKH/vận hành kiểm tra lại từ ảnh.
3. Khoảng hai tuần/lần, CSKH tự xếp lịch và nhắc tổng vệ sinh.
4. CSKH theo dõi lịch dọn và xác nhận thủ công phòng đã sẵn sàng.
5. Yêu cầu đặc biệt của khách được chuyển tiếp qua tin nhắn hoặc lịch dọn.
6. Sự cố được báo qua chat/sheet; kết quả sửa chữa không được cập nhật tập trung.
7. Bảo trì chủ yếu mang tính phản ứng hoặc phụ thuộc vào trí nhớ.
8. Quản gia báo vận hành khi vật tư gần hết để mua bổ sung.
9. CSKH phải phối hợp thủ công với Sales để dừng/mở bán phòng có sự cố.
10. Ảnh kiểm tra nằm trong nhóm Zalo; quản lý phải tự dò theo phòng.
11. Công việc được giao qua sheet/tin nhắn; tiến độ và phối hợp bị phân tán.
12. Founder/quản lý phải hỏi người hoặc kiểm tra nhiều nguồn để biết tình hình.
13. Sales phải theo dõi chat hoặc hỏi CSKH để biết phòng có thể bán hay không.

## 2. Mục tiêu sản phẩm

Zalo chỉ là kênh thông báo; hệ thống là nguồn dữ liệu chính duy nhất cho trạng thái vận hành.

Hệ thống phải nối được chuỗi nghiệp vụ:

`Booking → Lịch dọn → Thực hiện → QC → Trạng thái phòng → Khả năng mở bán`

Khi có sự cố:

`Báo lỗi → Chặn phòng → Work Order → Sửa chữa → Xác nhận → Gỡ chặn → Mở bán`

Mỗi công việc phải có tối thiểu: chi nhánh, phòng/khu vực, loại việc, người phụ trách,
deadline, trạng thái, bằng chứng, lịch sử thay đổi và kết quả cuối cùng.

### 2.1. Mô hình tổ chức và cô lập dữ liệu chi nhánh

- Bliss Home là nền tảng tổng, quản lý nhiều chi nhánh.
- Mỗi chi nhánh bắt buộc có đúng một chủ chi nhánh tại một thời điểm; việc đổi chủ phải có lịch sử và audit.
- Chủ chi nhánh là quyền theo quan hệ với chi nhánh, không phải role toàn cục trên tài khoản.
- Một tài khoản có thể sở hữu nhiều chi nhánh; quyền và dữ liệu vẫn được xác định riêng cho từng chi nhánh.
- Chủ chi nhánh được quản trị nhân sự, cấu hình, vận hành và tài chính của chi nhánh mình; không được xem dữ liệu chi nhánh khác nếu không có quan hệ quyền tương ứng.
- Founder/quản trị nền tảng tạo chi nhánh, chỉ định hoặc chuyển chủ và có quyền giám sát đa chi nhánh theo chính sách hệ thống.
- Booking, phòng, task, ảnh, sự cố, bảo trì, kho, nhân sự, doanh thu, chi phí, công nợ, quỹ và báo cáo đều phải gắn `branch_id`.
- Mọi selector/API/export/dashboard phải scope theo chi nhánh ở phía máy chủ; không dựa vào bộ lọc giao diện để bảo vệ dữ liệu.
- Quan hệ chéo giữa các bản ghi phải cùng chi nhánh. Giao dịch điều chuyển giữa hai chi nhánh, nếu có, phải là nghiệp vụ riêng có hai đầu và audit đầy đủ.
- Báo cáo tài chính mặc định chốt riêng theo chi nhánh; số liệu tổng hợp nhiều chi nhánh chỉ dành cho người có quyền nền tảng hoặc đồng thời có quyền ở tất cả chi nhánh liên quan.

## 3. Sáu phân hệ nghiệp vụ

### 3.1. Booking và điều phối

- Tổng hợp check-in/check-out theo ngày, chi nhánh và phòng.
- Cảnh báo booking thiếu phòng, trùng lịch hoặc chưa có lịch dọn.
- Sinh hoặc đề xuất task dọn từ booking.
- Reschedule/hủy task khi booking thay đổi.
- Chuyển yêu cầu đặc biệt vào task dưới dạng dữ liệu có cấu trúc.
- Cho phép nhập Excel/CSV trước; PMS/API/webhook triển khai sau.

### 3.2. Housekeeping và QC

- Tiếp tục dùng workflow, checklist, ảnh, QC, rework, SLA và offline hiện có.
- Tạo lịch tổng vệ sinh định kỳ thay vì để CSKH tự nhớ.
- Ảnh phải tra cứu được theo phòng, task, hạng mục, loại ảnh, ngày và người chụp.
- QC đạt mới loại bỏ blocker vệ sinh của phòng.

### 3.3. Sự cố và bảo trì

- `IssueTicket` là báo cáo vấn đề; `MaintenanceWorkOrder` là công việc giao cho thợ.
- Quản lý thiết bị/tài sản theo chi nhánh, phòng/khu vực và lịch sử sửa chữa.
- Work Order có người nhận, SLA, ảnh trước/sau, vật tư, chi phí và kết quả.
- Thợ báo hoàn thành không đồng nghĩa tự động gỡ chặn; vận hành phải xác nhận.
- Hỗ trợ kế hoạch bảo trì phòng ngừa và tự sinh Work Order định kỳ.

### 3.4. Kho và vật tư

- Danh mục vật tư và tồn theo kho/chi nhánh.
- Nhập, xuất, điều chỉnh và cấp vật tư theo task/work order.
- Mức tồn tối thiểu, cảnh báo sắp hết và đề nghị mua hàng.
- Lưu người yêu cầu, người duyệt, người nhận và mục đích sử dụng.

### 3.5. Trạng thái phòng và khả năng mở bán

Không dùng một trường trạng thái duy nhất cho mọi câu hỏi. Mỗi phòng có các trục:

- `cleanliness_status`: bẩn, đang dọn, chờ QC, sạch.
- `occupancy_status`: trống, đang có khách, sắp check-in.
- `maintenance_status`: bình thường, suy giảm, bị chặn.
- `sales_status`: mở bán, tạm dừng bán.

`ready_for_guest` được tính từ blocker, không cho người dùng tùy ý bật khi điều kiện chưa đạt:

- QC đã đạt hoặc policy không yêu cầu QC.
- Không có sự cố/Work Order đang chặn.
- Không bị quản lý khóa.
- Không thiếu vật tư bắt buộc.
- Không còn mutation/ảnh bắt buộc chờ đồng bộ.

Dừng bán phải có khoảng thời gian, lý do, nguồn gây chặn, người tạo và người xác nhận mở lại.

### 3.6. Trung tâm điều hành

- Founder: tổng quan đa chi nhánh, rủi ro, SLA, stop-sell, rework, bảo trì và tồn kho.
- Chủ chi nhánh: toàn quyền vận hành và tài chính trong đúng chi nhánh sở hữu.
- Quản lý: phân công, xử lý ngoại lệ và theo dõi tiến độ theo chi nhánh.
- CSKH: lịch booking, yêu cầu khách, phòng sắp check-in và readiness.
- Sales: chỉ đọc khả năng bán, blocker và thời điểm dự kiến mở lại.
- Quản gia/kỹ thuật/kho: hàng đợi công việc đúng vai trò trên web/mobile.

## 4. Ba màn hình ưu tiên

### 4.1. Lịch vận hành

- Bộ lọc ngày và chi nhánh.
- Booking theo giờ check-out/check-in.
- Task dọn liên quan và trạng thái hiện tại.
- Yêu cầu đặc biệt của khách.
- Cảnh báo chưa có lịch dọn, quá hạn hoặc nguy cơ trễ check-in.

### 4.2. Bảng trạng thái phòng

- Hiển thị dạng lưới theo chi nhánh/khu vực/tầng.
- Trạng thái vệ sinh, khách lưu trú, QC, sự cố chặn và readiness.
- Task đang mở, người phụ trách và thời điểm dự kiến sẵn sàng.
- Cho phép Sales/CSKH đọc cùng một kết quả thay vì hỏi qua chat.

### 4.3. Hồ sơ phòng 360°

- Booking hiện tại, gần nhất và sắp tới.
- Task dọn và QC.
- Gallery ảnh theo phòng/thời gian/hạng mục.
- Sự cố, yêu cầu vật tư và lịch sử trạng thái.
- Timeline chung ghi rõ ai làm gì và lúc nào.

## 5. Kiến trúc ứng dụng đích

- `reservations`: booking và tích hợp nguồn lịch.
- `housekeeping`: dọn phòng, checklist, ảnh, QC, SLA và offline.
- `maintenance`: tài sản, issue, work order và bảo trì định kỳ.
- `inventory`: danh mục, tồn kho, nhập/xuất và mua hàng.
- `room_operations`: readiness, blocker, lịch vận hành và phòng 360°.
- `integrations`: Zalo, PMS, email và webhook.
- `analytics`: chỉ số và dashboard tổng hợp.

Không chuyển model hiện có sang app mới chỉ để làm đẹp cấu trúc. Migration phải tiến hóa,
không đổi `app_label`/tên bảng hoặc reset dữ liệu đang có.

## 6. Domain event cần chuẩn hóa

- `BOOKING_CREATED`, `BOOKING_CHANGED`, `BOOKING_CANCELLED`.
- `CLEANING_TASK_GENERATED`, `CLEANING_QC_APPROVED`.
- `BLOCKING_ISSUE_CREATED`, `WORK_ORDER_COMPLETED`, `WORK_ORDER_VERIFIED`.
- `ROOM_READINESS_CHANGED`, `ROOM_STOP_SELL_STARTED`, `ROOM_STOP_SELL_ENDED`.
- `STOCK_BELOW_MINIMUM`, `SUPPLY_FULFILLED`.

Tiếp tục dùng Outbox Pattern để gửi thông báo/tích hợp mà không làm hỏng transaction nghiệp vụ.

## 7. Roadmap

### Nền tảng đa chi nhánh — phải hoàn tất trước module tài chính

- Bổ sung quan hệ chủ sở hữu cho `Branch` và quy trình chỉ định/chuyển chủ có audit.
- Scope toàn bộ màn hình, API và báo cáo theo ownership/membership tại server.
- Bổ sung test chống đọc, sửa, export và tổng hợp dữ liệu chéo chi nhánh.
- Chỉ bắt đầu sổ quỹ/doanh thu/chi phí sau khi lớp cô lập dữ liệu này đạt kiểm thử.

### Giai đoạn 1 — Trung tâm vận hành phòng

**Trạng thái: hoàn thành ngày 07/08/2026.**

- Lịch vận hành đọc từ Booking và Housekeeping task hiện có.
- Bảng trạng thái phòng với blocker/readiness được tính tập trung.
- Hồ sơ phòng 360° và gallery ảnh.
- Sau khi ba màn hình ổn định mới thêm tự động sinh/reschedule task từ Booking.

### Giai đoạn 2 — Stop-sell và Sales

**Trạng thái: hoàn thành ngày 07/08/2026.**

- Blocker engine chính thức.
- Stop-sell theo khoảng ngày và quy trình khóa/mở có audit.
- View read-only dành cho Sales.

### Giai đoạn 3 — Bảo trì

**Trạng thái: tiếp theo.**

- Asset, MaintenanceWorkOrder, thợ/đối tác và xác nhận hoàn thành.
- Lịch bảo trì phòng ngừa.

### Giai đoạn 4 — Kho

- Inventory item, stock balance/movement, min stock và purchase request.

### Giai đoạn 5 — Tích hợp và phân tích

- Dashboard Founder đa chi nhánh.
- Tích hợp PMS/nguồn Booking và Zalo làm kênh thông báo/deep link.

## 8. Chỉ số thành công

- Tỷ lệ booking có task dọn được tạo đúng hạn.
- Tỷ lệ phòng sẵn sàng trước check-in.
- Số phút stop-sell do vệ sinh/bảo trì.
- Thời gian xử lý sự cố trung bình và tỷ lệ tái phát.
- Tỷ lệ QC không đạt/làm lại.
- Số lần thiếu vật tư và thời gian chờ cấp.
- Tỷ lệ công việc/ảnh được ghi nhận trong hệ thống thay vì chỉ tồn tại trên Zalo.
- Số lần Founder/CSKH/Sales phải hỏi thủ công về trạng thái phòng.

## 9. Nguyên tắc triển khai

- Dữ liệu hệ thống là nguồn sự thật; Zalo không giữ trạng thái nghiệp vụ.
- Mọi thay đổi readiness/stop-sell đều có lý do và audit.
- Không đánh dấu phòng sẵn sàng khi còn blocker.
- Không xóa/reset dữ liệu hiện có để triển khai model mới.
- Quyền luôn theo vai trò và phạm vi chi nhánh.
- Không dùng global role để suy ra quyền chủ chi nhánh; phải kiểm tra ownership/membership cụ thể.
- Tài chính và vận hành của mỗi chi nhánh phải được cô lập ở model, service, selector, API và export.
- UI quản trị và API/mobile dùng chung selector/service nghiệp vụ.
- Cảnh báo không chỉ dựa vào màu; phải có chữ/icon.
- Chức năng mới có test về scope, concurrency và state transition tương ứng.
