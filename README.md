# QUẢN GIA XEM DANH SÁCH TASK THEO CA/CHI NHÁNH, NHẬN VIỆC VÀ CẬP NHẬT TIẾN ĐỘ TỪNG PHÒNG

## 1. Mục đích

Cho phép Quản gia:

* Xem các công việc được giao hoặc đang chờ nhận theo ca làm việc.
* Chỉ xem công việc thuộc chi nhánh được phân quyền.
* Nhận công việc dọn phòng.
* Bắt đầu thực hiện công việc.
* Cập nhật tiến độ theo thời gian thực.
* Hoàn thành checklist của từng phòng.
* Gửi công việc sang bước QC.
* Báo sự cố, thiếu vật tư hoặc không thể thực hiện công việc.

Chức năng giúp Quản lý theo dõi chính xác trạng thái từng phòng và hạn chế việc giao việc qua Zalo hoặc ghi nhận thủ công.

---

## 2. Người sử dụng

### Người dùng chính

* Quản gia.
* Nhân viên Housekeeping.
* Trưởng nhóm Housekeeping.

### Người dùng liên quan

* Điều phối.
* Quản lý chi nhánh.
* QC.
* Kỹ thuật.
* Nhân viên kho.

---

## 3. Điều kiện trước

Để sử dụng chức năng, người dùng phải đáp ứng các điều kiện sau:

* Đã đăng nhập.
* Tài khoản đang ở trạng thái hoạt động.
* Được cấp vai trò Housekeeping hoặc vai trò có quyền tương đương.
* Được phân vào ít nhất một chi nhánh.
* Có ca làm việc đang hoạt động hoặc được phép nhận việc ngoài ca.
* Phòng và task đã tồn tại trong hệ thống.
* Task chưa bị hủy hoặc hoàn thành.
* Thiết bị của người dùng có kết nối mạng hoặc đã tải dữ liệu để làm việc ngoại tuyến.

---

## 4. Định nghĩa Task dọn phòng

Một task dọn phòng là công việc được tạo cho một phòng tại một thời điểm xác định.

Task có thể được sinh từ:

* Booking check-out.
* Booking sắp check-in.
* Khách yêu cầu dọn phòng.
* Lịch dọn định kỳ.
* Deep cleaning.
* QC yêu cầu làm lại.
* Quản lý tạo thủ công.
* Sự cố cần xử lý vệ sinh.
* Thay đổi trạng thái phòng.

Mỗi task phải thuộc một phòng và một chi nhánh cụ thể.

---

## 5. Các loại task

Hệ thống hỗ trợ tối thiểu các loại task sau:

### 5.1. Dọn phòng sau check-out

Áp dụng khi khách đã trả phòng.

Mục tiêu:

Đưa phòng từ trạng thái `DIRTY` hoặc `WAITING_CLEANING` sang trạng thái sẵn sàng để QC.

### 5.2. Dọn phòng đang có khách

Áp dụng khi khách đang lưu trú và yêu cầu dọn phòng.

Ví dụ:

* Thay khăn.
* Dọn rác.
* Bổ sung nước.
* Vệ sinh cơ bản.

### 5.3. Chuẩn bị phòng check-in

Kiểm tra và bổ sung các hạng mục trước khi khách nhận phòng.

### 5.4. Deep cleaning

Vệ sinh chuyên sâu theo lịch hoặc theo yêu cầu của Quản lý.

### 5.5. Dọn lại sau QC không đạt

Được tạo khi QC từ chối kết quả dọn phòng.

Task phải liên kết với lần kiểm tra QC không đạt.

### 5.6. Công việc vệ sinh định kỳ

Ví dụ:

* Giặt rèm.
* Vệ sinh máy lạnh.
* Vệ sinh ban công.
* Vệ sinh khu vực khó tiếp cận.

---

## 6. Trạng thái Task

Task có các trạng thái sau:

| Trạng thái     | Mã trạng thái        | Ý nghĩa                                          |
| -------------- | -------------------- | ------------------------------------------------ |
| Chờ phân công  | `UNASSIGNED`         | Task chưa được giao cho nhân viên                |
| Đã phân công   | `ASSIGNED`           | Task đã được giao cho một nhân viên              |
| Chờ nhận việc  | `PENDING_ACCEPTANCE` | Nhân viên chưa xác nhận nhận việc                |
| Đã nhận việc   | `ACCEPTED`           | Nhân viên đã nhận task                           |
| Đang thực hiện | `IN_PROGRESS`        | Nhân viên đã bắt đầu làm                         |
| Tạm dừng       | `PAUSED`             | Task đang tạm dừng                               |
| Chờ hỗ trợ     | `WAITING_SUPPORT`    | Không thể tiếp tục vì thiếu vật tư hoặc có sự cố |
| Đã hoàn thành  | `COMPLETED`          | Quản gia đã hoàn tất công việc                   |
| Chờ QC         | `WAITING_QC`         | Đã gửi sang QC                                   |
| QC không đạt   | `QC_REJECTED`        | QC yêu cầu làm lại                               |
| QC đạt         | `QC_APPROVED`        | Công việc đã được nghiệm thu                     |
| Đã hủy         | `CANCELLED`          | Task bị hủy                                      |
| Quá hạn        | `OVERDUE`            | Task vượt thời hạn SLA                           |

Một task có thể đồng thời mang cờ `OVERDUE`, nhưng trạng thái nghiệp vụ chính vẫn là `ASSIGNED`, `IN_PROGRESS` hoặc trạng thái tương ứng.

---

## 7. Trạng thái phòng liên quan

Trạng thái phòng phải được đồng bộ theo tiến độ task.

| Trạng thái Task                      | Trạng thái phòng đề xuất               |
| ------------------------------------ | -------------------------------------- |
| Task được tạo                        | `WAITING_CLEANING`                     |
| Quản gia bắt đầu                     | `CLEANING`                             |
| Task tạm dừng do sự cố               | `CLEANING_BLOCKED`                     |
| Quản gia hoàn thành                  | `WAITING_QC`                           |
| QC không đạt                         | `REWORK_REQUIRED`                      |
| QC đạt                               | `READY`                                |
| Task bị hủy và chưa có task thay thế | Giữ hoặc tính lại theo booking/thực tế |

Hệ thống không được chuyển phòng sang `READY` chỉ vì Quản gia bấm hoàn thành. Phòng chỉ chuyển sang `READY` sau khi QC đạt, trừ khi loại task được cấu hình không yêu cầu QC.

---

# 8. Màn hình danh sách Task

## 8.1. Mục đích

Hiển thị các task mà Quản gia được phép xem và thực hiện.

## 8.2. Các tab chính

Màn hình có thể gồm các tab:

* Việc của tôi.
* Việc đang chờ nhận.
* Đang thực hiện.
* Chờ hỗ trợ.
* Chờ QC.
* Cần làm lại.
* Đã hoàn thành.

## 8.3. Thông tin hiển thị trên mỗi Task

Mỗi task trong danh sách hiển thị:

* Mã task.
* Mã phòng.
* Tên phòng.
* Chi nhánh.
* Tầng hoặc khu vực.
* Loại task.
* Mức ưu tiên.
* Thời gian dự kiến bắt đầu.
* Thời hạn hoàn thành.
* Thời gian còn lại hoặc thời gian quá hạn.
* Trạng thái task.
* Tên nhân viên được giao.
* Trạng thái phòng.
* Thời gian check-in tiếp theo nếu có.
* Ghi chú quan trọng.
* Cảnh báo khách đang ở trong phòng.
* Cảnh báo có yêu cầu đặc biệt.
* Số lượng checklist đã hoàn thành.
* Số ảnh bắt buộc đã tải.
* Trạng thái đồng bộ dữ liệu.

## 8.4. Màu cảnh báo đề xuất

* Bình thường: không cảnh báo.
* Sắp quá hạn: cảnh báo vàng.
* Quá hạn: cảnh báo đỏ.
* Task ưu tiên cao: biểu tượng ưu tiên.
* Task chờ hỗ trợ: cảnh báo cam.
* QC yêu cầu làm lại: cảnh báo đỏ kèm lý do.

Không được chỉ dùng màu để truyền đạt trạng thái; phải có thêm chữ hoặc biểu tượng.

---

# 9. Bộ lọc và tìm kiếm

Người dùng có thể lọc task theo:

* Ngày.
* Ca làm việc.
* Chi nhánh.
* Khu vực.
* Tầng.
* Loại phòng.
* Loại task.
* Trạng thái.
* Mức ưu tiên.
* Người được phân công.
* Task quá hạn.
* Task sắp có khách check-in.
* Task QC yêu cầu làm lại.

Tìm kiếm theo:

* Mã phòng.
* Tên phòng.
* Mã task.
* Mã booking.
* Tên khách nếu được cấp quyền.
* Số điện thoại khách nếu được cấp quyền.

Quản gia chỉ được tìm kiếm dữ liệu trong phạm vi chi nhánh được phân quyền.

---

# 10. Phân loại Task theo ca

## 10.1. Quy tắc xác định ca

Task được hiển thị theo ca dựa trên:

* Thời gian dự kiến bắt đầu.
* Ca của nhân viên.
* Chi nhánh của ca.
* Khu vực phụ trách.
* Kỹ năng hoặc nhóm nhân viên phù hợp.
* Thời gian check-in tiếp theo của phòng.

## 10.2. Trường hợp task kéo dài qua nhiều ca

Nếu task chưa hoàn thành khi ca kết thúc:

* Nhân viên có thể tiếp tục nếu được phép.
* Quản lý có thể chuyển task sang ca tiếp theo.
* Task phải giữ toàn bộ tiến độ đã thực hiện.
* Hệ thống ghi nhận người thực hiện trước và người nhận bàn giao.
* Checklist đã hoàn thành không bị mất.
* Các hạng mục bắt buộc có thể cần xác nhận lại nếu cấu hình yêu cầu.

## 10.3. Nhận task ngoài ca

Mặc định Quản gia không được nhận task ngoài ca.

Có thể cho phép nếu:

* Quản lý phân công trực tiếp.
* Nhân viên đang tăng ca.
* Task có mức độ khẩn cấp.
* Chi nhánh không còn nhân viên đang trong ca.

Mọi lần nhận task ngoài ca phải được ghi log.

---

# 11. Luồng xem danh sách Task

## Bước 1: Mở màn hình công việc

Quản gia chọn menu:

“Công việc” hoặc “Task của tôi”.

## Bước 2: Hệ thống xác định phạm vi

Hệ thống lấy:

* User ID.
* Vai trò.
* Chi nhánh được phân quyền.
* Ca làm hiện tại.
* Khu vực phụ trách.
* Task đã giao.
* Task đang mở cho phép tự nhận.

## Bước 3: Tải danh sách

Hệ thống trả danh sách task theo thứ tự ưu tiên.

Thứ tự đề xuất:

1. Task QC yêu cầu làm lại.
2. Task sắp có khách check-in.
3. Task quá hạn.
4. Task ưu tiên khẩn cấp.
5. Task đã được giao trực tiếp.
6. Task còn lại theo thời hạn gần nhất.

## Bước 4: Hiển thị dữ liệu

Hệ thống hiển thị danh sách theo bộ lọc mặc định:

* Ngày hiện tại.
* Ca hiện tại.
* Chi nhánh hiện tại.
* Chưa hoàn thành.

---

# 12. Luồng nhận việc

## 12.1. Điều kiện được nhận việc

Quản gia được nhận task khi:

* Task đang ở trạng thái `UNASSIGNED` hoặc `PENDING_ACCEPTANCE`.
* Task thuộc chi nhánh được phân quyền.
* Task chưa được người khác nhận.
* Task chưa bị hủy.
* Task không bị khóa bởi Quản lý.
* Người dùng đang trong ca hoặc có quyền nhận ngoài ca.
* Người dùng không vượt số lượng task đồng thời được cấu hình.

## 12.2. Luồng xử lý

1. Quản gia mở chi tiết task.
2. Chọn “Nhận việc”.
3. Hệ thống kiểm tra trạng thái hiện tại của task.
4. Hệ thống kiểm tra quyền và ca làm việc.
5. Hệ thống khóa bản ghi trong thời gian xử lý.
6. Nếu hợp lệ:

   * Gán `assignee_id`.
   * Ghi `accepted_at`.
   * Chuyển trạng thái thành `ACCEPTED`.
   * Ghi Activity Log.
   * Thông báo cho Điều phối hoặc Quản lý nếu cần.
7. Nếu task đã được người khác nhận:

   * Không ghi đè người nhận.
   * Hiển thị thông báo task không còn khả dụng.

## 12.3. Xử lý hai người nhận cùng lúc

Hệ thống phải xử lý cạnh tranh dữ liệu.

Chỉ một người được nhận task thành công.

Người còn lại nhận lỗi:

“Công việc đã được nhân viên khác nhận.”

Backend phải sử dụng:

* Database transaction.
* Optimistic locking bằng version.
* Hoặc row-level lock.

Không được dựa hoàn toàn vào trạng thái hiển thị trên giao diện.

---

# 13. Luồng từ chối hoặc trả lại Task

Nếu được cấu hình, Quản gia có thể từ chối hoặc trả lại task trước khi bắt đầu.

Người dùng phải chọn lý do:

* Không thuộc ca làm.
* Không thuộc khu vực phụ trách.
* Đang xử lý task ưu tiên khác.
* Không đủ dụng cụ.
* Không đủ kỹ năng.
* Phòng chưa thể tiếp cận.
* Lý do khác.

Sau khi trả lại:

* Xóa hoặc kết thúc phân công hiện tại.
* Chuyển task về `UNASSIGNED`.
* Lưu lý do.
* Thông báo cho Điều phối.
* Ghi Activity Log.

Quản gia không được tự trả lại task sau khi đã bắt đầu, trừ khi có quyền hoặc được Quản lý duyệt.

---

# 14. Luồng bắt đầu thực hiện

## 14.1. Điều kiện

Task phải ở trạng thái:

* `ACCEPTED`.
* Hoặc `QC_REJECTED` và đã được giao lại.

## 14.2. Luồng xử lý

1. Quản gia đến phòng.
2. Mở task.
3. Chọn “Bắt đầu”.
4. Hệ thống có thể yêu cầu:

   * Quét QR tại phòng.
   * Kết nối Wi-Fi của chi nhánh.
   * Xác nhận GPS.
   * Chụp ảnh trước khi dọn.
5. Hệ thống kiểm tra phòng có thể thực hiện hay không.
6. Ghi `started_at`.
7. Chuyển trạng thái task thành `IN_PROGRESS`.
8. Chuyển trạng thái phòng thành `CLEANING`.
9. Bắt đầu tính thời gian thực hiện.
10. Ghi Activity Log.

## 14.3. Trường hợp phòng đang có khách

Nếu khách đang ở trong phòng:

* Hiển thị cảnh báo.
* Yêu cầu xác nhận khách đã đồng ý cho vào.
* Có thể yêu cầu nhập ghi chú.
* Không hiển thị dữ liệu nhạy cảm không cần thiết của khách.

## 14.4. Trường hợp có người khác đang xử lý

Nếu task hoặc phòng đang được một nhân viên khác xử lý:

* Không cho bắt đầu.
* Hiển thị tên người đang thực hiện nếu được phép.
* Cho phép gọi hỗ trợ hoặc gửi yêu cầu bàn giao.

---

# 15. Màn hình chi tiết Task

Màn hình chi tiết gồm các phần:

## 15.1. Thông tin chung

* Mã task.
* Loại task.
* Mức ưu tiên.
* Trạng thái.
* Chi nhánh.
* Phòng.
* Tầng/khu vực.
* Thời gian tạo.
* Thời hạn hoàn thành.
* SLA.
* Người tạo.
* Người giao việc.
* Người đang thực hiện.

## 15.2. Thông tin phòng

* Mã phòng.
* Loại phòng.
* Trạng thái phòng.
* Booking hiện tại.
* Giờ check-out.
* Giờ check-in tiếp theo.
* Số khách dự kiến.
* Yêu cầu đặc biệt.
* Cảnh báo thiết bị hỏng.
* Cảnh báo phòng khóa hoặc đang sửa.

## 15.3. Checklist

Hiển thị các nhóm checklist:

* Phòng ngủ.
* Phòng tắm.
* Khu vực bếp.
* Ban công.
* Đồ amenities.
* Minibar.
* Thiết bị.
* An toàn.
* Ảnh trước/sau.
* Ghi chú.

## 15.4. Hình ảnh

* Ảnh trước khi dọn.
* Ảnh sau khi dọn.
* Ảnh sự cố.
* Ảnh thiếu vật tư.
* Ảnh QC không đạt.

## 15.5. Timeline

Hiển thị:

* Task được tạo.
* Giao cho ai.
* Thời điểm nhận.
* Thời điểm bắt đầu.
* Các lần tạm dừng.
* Sự cố phát sinh.
* Thời điểm hoàn thành.
* Kết quả QC.
* Các lần làm lại.

---

# 16. Cập nhật tiến độ từng phòng

## 16.1. Mục đích

Cho phép Quản gia ghi nhận tiến độ thực tế trong quá trình dọn, thay vì chỉ có trạng thái bắt đầu và hoàn thành.

## 16.2. Cách cập nhật

Tiến độ có thể được tính theo:

* Số mục checklist đã hoàn thành.
* Các giai đoạn công việc.
* Tỷ lệ phần trăm.
* Trạng thái thủ công.

Khuyến nghị ưu tiên tính theo checklist thay vì cho người dùng nhập phần trăm tự do.

Công thức đề xuất:

`Tiến độ = Số checklist bắt buộc đã hoàn thành / Tổng checklist bắt buộc × 100%`

Checklist tùy chọn không bắt buộc tính vào tiến độ chính.

## 16.3. Các mốc tiến độ

Ví dụ:

* 0%: Chưa bắt đầu.
* 1–25%: Đang chuẩn bị.
* 26–50%: Đang vệ sinh chính.
* 51–75%: Đang bổ sung vật tư và kiểm tra thiết bị.
* 76–99%: Đang kiểm tra cuối.
* 100%: Hoàn thành checklist, chờ gửi QC.

## 16.4. Đồng bộ tiến độ

Mỗi lần người dùng:

* Tick checklist.
* Bỏ tick checklist.
* Thêm ảnh.
* Báo lỗi.
* Tạm dừng.
* Tiếp tục.

Hệ thống cập nhật:

* `progress_percent`.
* `last_progress_at`.
* `updated_by`.
* Timeline của task.

Không cần gửi thông báo cho Quản lý sau mỗi checklist, nhưng Dashboard phải xem được tiến độ gần thời gian thực.

---

# 17. Checklist trong quá trình thực hiện

## 17.1. Quy tắc

Mỗi task sử dụng một phiên bản checklist xác định tại thời điểm tạo task.

Nếu Admin thay đổi checklist sau đó:

* Task cũ vẫn dùng phiên bản cũ.
* Task mới dùng phiên bản mới.
* Không thay đổi nội dung task đang thực hiện.

## 17.2. Các loại checklist item

* Checkbox đạt/không đạt.
* Có/không.
* Nhập số lượng.
* Nhập văn bản.
* Chụp ảnh.
* Chọn một giá trị.
* Chọn nhiều giá trị.
* Xác nhận thiết bị hoạt động.
* Quét mã QR hoặc barcode.

## 17.3. Checklist bắt buộc

Không được hoàn thành task nếu:

* Còn checklist bắt buộc chưa xử lý.
* Chưa đủ ảnh bắt buộc.
* Có mục “Không đạt” nhưng chưa tạo ticket hoặc ghi lý do.
* Có thiếu vật tư chưa được xử lý theo quy trình.
* Chưa xác nhận kiểm tra cuối phòng.

---

# 18. Chụp và tải ảnh

## 18.1. Loại ảnh

* Ảnh trước khi dọn.
* Ảnh sau khi dọn.
* Ảnh theo từng khu vực.
* Ảnh thiết bị hỏng.
* Ảnh vật tư thiếu.
* Ảnh bằng chứng hoàn thành.
* Ảnh phục vụ QC.

## 18.2. Quy tắc

* Có thể yêu cầu chụp trực tiếp từ camera.
* Không cho chọn ảnh cũ từ thư viện đối với loại bằng chứng bắt buộc, nếu cấu hình yêu cầu.
* Ảnh phải gắn:

  * Task ID.
  * Room ID.
  * User ID.
  * Thời gian.
  * Loại ảnh.
  * Checklist item liên quan.
* Ảnh phải được nén trước khi tải lên nhưng vẫn đủ chất lượng để QC.
* Ảnh chưa đồng bộ phải có trạng thái rõ ràng.
* Không cho hoàn thành nếu ảnh bắt buộc chưa tải thành công, trừ trường hợp offline có cơ chế chờ đồng bộ được chấp nhận.

---

# 19. Tạm dừng và tiếp tục Task

## 19.1. Lý do tạm dừng

* Khách chưa rời phòng.
* Khách yêu cầu quay lại sau.
* Thiếu vật tư.
* Thiết bị hỏng.
* Chờ Kỹ thuật.
* Chờ Quản lý xác nhận.
* Có công việc ưu tiên cao hơn.
* Nghỉ giữa ca.
* Lý do khác.

## 19.2. Luồng tạm dừng

1. Chọn “Tạm dừng”.
2. Chọn lý do.
3. Nhập ghi chú nếu cần.
4. Chụp ảnh nếu lý do yêu cầu bằng chứng.
5. Hệ thống ghi thời điểm tạm dừng.
6. Chuyển trạng thái thành `PAUSED` hoặc `WAITING_SUPPORT`.
7. Dừng bộ đếm thời gian thao tác nếu SLA được cấu hình loại trừ thời gian chờ.
8. Thông báo cho người liên quan.

## 19.3. Tiếp tục

1. Chọn “Tiếp tục”.
2. Hệ thống kiểm tra điều kiện chặn đã được xử lý.
3. Chuyển trạng thái về `IN_PROGRESS`.
4. Ghi thời gian tiếp tục.
5. Tiếp tục tính thời lượng.

---

# 20. Báo thiếu vật tư

Trong quá trình dọn, Quản gia có thể báo:

* Thiếu khăn.
* Thiếu ga.
* Thiếu nước.
* Thiếu dầu gội.
* Thiếu giấy.
* Thiếu dụng cụ vệ sinh.
* Thiếu minibar.
* Vật tư khác.

Thông tin cần nhập:

* Loại vật tư.
* Số lượng cần.
* Mức độ khẩn cấp.
* Ghi chú.
* Ảnh nếu có.
* Kho hoặc vị trí yêu cầu cấp.

Hệ thống có thể:

* Tạo yêu cầu cấp vật tư.
* Thông báo cho kho.
* Chuyển task sang `WAITING_SUPPORT`.
* Cho phép tiếp tục các checklist không bị ảnh hưởng.
* Ghi thời gian chờ vật tư.

---

# 21. Báo sự cố

Nếu phát hiện thiết bị hoặc tài sản hỏng:

1. Quản gia chọn “Báo sự cố”.
2. Chọn thiết bị hoặc khu vực.
3. Chọn loại sự cố.
4. Nhập mô tả.
5. Chọn mức độ ảnh hưởng.
6. Chụp ảnh/video.
7. Hệ thống tạo ticket.
8. Ticket liên kết với:

   * Task.
   * Phòng.
   * Booking nếu liên quan.
   * Thiết bị nếu xác định được.
9. Hệ thống xác định task có thể tiếp tục hay phải chờ xử lý.

Ví dụ:

* Bóng đèn phụ hỏng: Có thể tiếp tục và gửi QC kèm ticket.
* Khóa cửa hỏng: Không được chuyển phòng sang Ready.
* Rò điện: Dừng task, khóa phòng và báo khẩn cấp.

---

# 22. Hoàn thành Task

## 22.1. Điều kiện hoàn thành

Task chỉ được hoàn thành khi:

* Tất cả checklist bắt buộc đã xử lý.
* Các ảnh bắt buộc đã được chụp.
* Không còn lỗi chặn chưa xử lý.
* Các mục không đạt đã có ticket hoặc lý do được chấp nhận.
* Người dùng đang là người thực hiện task.
* Task đang ở `IN_PROGRESS`.
* Không có phiên bản dữ liệu mới hơn gây xung đột.
* Đã xác nhận kiểm tra cuối.

## 22.2. Luồng xử lý

1. Quản gia chọn “Hoàn thành”.
2. Hệ thống kiểm tra checklist.
3. Hệ thống kiểm tra ảnh.
4. Hệ thống kiểm tra ticket/sự cố.
5. Hiển thị bản tóm tắt:

   * Thời gian thực hiện.
   * Checklist hoàn thành.
   * Vật tư sử dụng.
   * Sự cố phát hiện.
   * Ảnh bằng chứng.
6. Quản gia xác nhận.
7. Hệ thống ghi `completed_at`.
8. Chuyển trạng thái task thành `COMPLETED`.
9. Nếu cần QC:

   * Chuyển ngay thành `WAITING_QC`.
   * Tạo QC task.
   * Chuyển trạng thái phòng thành `WAITING_QC`.
10. Nếu không cần QC:

* Chuyển task thành `QC_APPROVED` hoặc trạng thái kết thúc tương đương.
* Chuyển phòng sang `READY`.

11. Ghi Activity Log.
12. Gửi thông báo cho QC hoặc Quản lý.

---

# 23. Luồng QC yêu cầu làm lại

Khi QC không đạt:

* Task chuyển sang `QC_REJECTED`.
* Phòng chuyển sang `REWORK_REQUIRED`.
* Quản gia nhận thông báo.
* Hiển thị:

  * Các checklist không đạt.
  * Ảnh QC.
  * Lý do.
  * Ghi chú.
  * Thời hạn phải xử lý lại.

Quản gia chọn:

“Bắt đầu làm lại”.

Hệ thống:

* Tăng số lần làm lại.
* Ghi `rework_started_at`.
* Chuyển task về `IN_PROGRESS`.
* Chỉ mở các mục cần làm lại hoặc toàn bộ checklist tùy cấu hình.

Sau khi làm lại:

* Chụp ảnh mới.
* Hoàn thành các checklist bị từ chối.
* Gửi QC lại.

Hệ thống phải lưu riêng từng lần QC và từng lần làm lại, không ghi đè dữ liệu cũ.

---

# 24. Quy tắc phân quyền

## Quản gia

Được phép:

* Xem task thuộc phạm vi được cấp.
* Nhận task được phép tự nhận.
* Bắt đầu task của mình.
* Cập nhật checklist.
* Chụp ảnh.
* Báo vật tư.
* Báo sự cố.
* Tạm dừng.
* Hoàn thành.
* Xem lịch sử task mình tham gia.

Không được phép:

* Sửa SLA.
* Xóa task.
* Thay đổi phòng của task.
* Tự duyệt QC.
* Chuyển task sang nhân viên khác nếu không có quyền.
* Sửa thời gian hệ thống đã ghi.
* Thay đổi checklist đã được cấu hình.

## Trưởng nhóm Housekeeping

Ngoài quyền Quản gia, có thể:

* Xem task của nhóm.
* Phân công hoặc điều chuyển task.
* Xem tiến độ nhân viên.
* Hỗ trợ xác nhận trường hợp đặc biệt.
* Chấp thuận một số lý do tạm dừng nếu được cấu hình.

## Quản lý

Có thể:

* Xem toàn bộ task thuộc chi nhánh.
* Tạo, giao, chuyển và hủy task.
* Điều chỉnh ưu tiên.
* Xử lý ngoại lệ.
* Xem báo cáo SLA và hiệu suất.

---

# 25. Quy tắc SLA

Mỗi task có thể có:

* Thời gian dự kiến bắt đầu.
* Thời hạn nhận việc.
* Thời hạn bắt đầu.
* Thời hạn hoàn thành.
* Thời lượng tiêu chuẩn.
* Thời gian check-in tiếp theo.

Ví dụ:

* Task được tạo lúc 10:00.
* Phải nhận trong 5 phút.
* Phải bắt đầu trong 15 phút.
* Phải hoàn thành trong 45 phút.
* Khách tiếp theo check-in lúc 12:00.

Hệ thống cảnh báo:

* Sắp quá thời hạn nhận.
* Quá thời hạn nhận.
* Sắp quá thời hạn bắt đầu.
* Quá thời hạn hoàn thành.
* Có nguy cơ không kịp check-in.

Escalation đề xuất:

* Trễ 5 phút: Nhắc Quản gia.
* Trễ 15 phút: Báo Trưởng nhóm.
* Trễ 30 phút: Báo Quản lý.
* Có nguy cơ ảnh hưởng check-in: Đánh dấu khẩn cấp.

---

# 26. Notification

Quản gia nhận thông báo khi:

* Có task mới được giao.
* Có task mới cho phép tự nhận.
* Task sắp đến giờ bắt đầu.
* Task sắp quá hạn.
* Task đã quá hạn.
* Task bị chuyển giao.
* Yêu cầu vật tư đã được xử lý.
* Ticket liên quan đã được xử lý.
* QC không đạt.
* Task bị hủy.
* Quản lý gửi ghi chú mới.

QC nhận thông báo khi:

* Quản gia hoàn thành task.
* Task sẵn sàng kiểm tra.
* Task ưu tiên cao.
* Phòng sắp có khách check-in.

---

# 27. API đề xuất

## 27.1. Lấy danh sách Task

`GET /api/v1/housekeeping/tasks`

Query parameters:

```text
date=2026-08-04
shiftId=SHIFT_MORNING
branchId=BRANCH_01
status=ASSIGNED,IN_PROGRESS
assignee=me
page=1
limit=20
```

Response:

```json
{
  "success": true,
  "data": [
    {
      "id": "TASK_001",
      "room": {
        "id": "ROOM_101",
        "code": "A101",
        "name": "Phòng A101",
        "floor": "Tầng 1"
      },
      "branch": {
        "id": "BRANCH_01",
        "name": "Bliss Home Đà Lạt"
      },
      "taskType": "CHECKOUT_CLEANING",
      "priority": "HIGH",
      "status": "ASSIGNED",
      "progressPercent": 0,
      "scheduledStartAt": "2026-08-04T10:00:00+07:00",
      "dueAt": "2026-08-04T10:45:00+07:00",
      "nextCheckinAt": "2026-08-04T12:00:00+07:00",
      "assignee": {
        "id": "USER_01",
        "name": "Nguyễn Thị Hương"
      },
      "checklistSummary": {
        "totalRequired": 20,
        "completedRequired": 0
      },
      "version": 1
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 12
  }
}
```

---

## 27.2. Nhận Task

`POST /api/v1/housekeeping/tasks/{taskId}/accept`

Request:

```json
{
  "version": 1
}
```

Response:

```json
{
  "success": true,
  "data": {
    "taskId": "TASK_001",
    "status": "ACCEPTED",
    "assigneeId": "USER_01",
    "acceptedAt": "2026-08-04T10:02:00+07:00",
    "version": 2
  }
}
```

---

## 27.3. Bắt đầu Task

`POST /api/v1/housekeeping/tasks/{taskId}/start`

Request:

```json
{
  "version": 2,
  "roomVerification": {
    "method": "QR_CODE",
    "value": "ROOM_A101_QR"
  },
  "location": {
    "latitude": 11.9404,
    "longitude": 108.4583,
    "accuracyMeters": 20
  }
}
```

---

## 27.4. Cập nhật checklist

`PATCH /api/v1/housekeeping/tasks/{taskId}/checklist-items/{itemId}`

Request:

```json
{
  "status": "COMPLETED",
  "value": true,
  "note": null,
  "version": 3
}
```

Response:

```json
{
  "success": true,
  "data": {
    "itemId": "ITEM_01",
    "status": "COMPLETED",
    "progressPercent": 35,
    "taskVersion": 4
  }
}
```

---

## 27.5. Tạm dừng Task

`POST /api/v1/housekeeping/tasks/{taskId}/pause`

Request:

```json
{
  "reasonCode": "WAITING_SUPPLIES",
  "note": "Thiếu 2 khăn tắm",
  "version": 4
}
```

---

## 27.6. Tiếp tục Task

`POST /api/v1/housekeeping/tasks/{taskId}/resume`

Request:

```json
{
  "version": 5
}
```

---

## 27.7. Báo thiếu vật tư

`POST /api/v1/housekeeping/tasks/{taskId}/supply-requests`

Request:

```json
{
  "items": [
    {
      "inventoryItemId": "ITEM_TOWEL",
      "quantity": 2,
      "unit": "Cái"
    }
  ],
  "priority": "HIGH",
  "note": "Cần trước khi hoàn thành phòng"
}
```

---

## 27.8. Báo sự cố

`POST /api/v1/housekeeping/tasks/{taskId}/issues`

Request:

```json
{
  "roomId": "ROOM_101",
  "deviceId": "DEVICE_AC_101",
  "issueType": "DEVICE_NOT_WORKING",
  "severity": "HIGH",
  "description": "Máy lạnh không khởi động",
  "blocksRoomReady": true,
  "attachmentIds": [
    "ATTACHMENT_001"
  ]
}
```

---

## 27.9. Hoàn thành Task

`POST /api/v1/housekeeping/tasks/{taskId}/complete`

Request:

```json
{
  "version": 12,
  "finalNote": "Đã hoàn thành toàn bộ checklist",
  "confirmFinalInspection": true
}
```

Response:

```json
{
  "success": true,
  "data": {
    "taskId": "TASK_001",
    "status": "WAITING_QC",
    "roomStatus": "WAITING_QC",
    "completedAt": "2026-08-04T10:42:00+07:00",
    "qcTaskId": "QC_TASK_001"
  }
}
```

---

# 28. Mã lỗi đề xuất

| Mã lỗi                           | Ý nghĩa                                      |
| -------------------------------- | -------------------------------------------- |
| `TASK_NOT_FOUND`                 | Không tìm thấy task                          |
| `TASK_ACCESS_DENIED`             | Không có quyền truy cập task                 |
| `TASK_ALREADY_ASSIGNED`          | Task đã được người khác nhận                 |
| `TASK_INVALID_STATUS`            | Trạng thái hiện tại không cho phép thao tác  |
| `TASK_VERSION_CONFLICT`          | Dữ liệu task đã được cập nhật bởi người khác |
| `USER_NOT_ON_SHIFT`              | Người dùng không trong ca                    |
| `USER_BRANCH_NOT_ALLOWED`        | Không có quyền tại chi nhánh                 |
| `TASK_CONCURRENT_LIMIT_EXCEEDED` | Vượt số task được làm đồng thời              |
| `ROOM_NOT_ACCESSIBLE`            | Không thể tiếp cận phòng                     |
| `ROOM_VERIFICATION_FAILED`       | Xác minh phòng thất bại                      |
| `CHECKLIST_REQUIRED_INCOMPLETE`  | Chưa hoàn tất checklist bắt buộc             |
| `REQUIRED_PHOTO_MISSING`         | Thiếu ảnh bắt buộc                           |
| `BLOCKING_ISSUE_EXISTS`          | Còn sự cố chặn hoàn thành                    |
| `SUPPLY_REQUEST_PENDING`         | Yêu cầu vật tư chưa hoàn tất                 |
| `TASK_ALREADY_COMPLETED`         | Task đã hoàn thành                           |
| `TASK_CANCELLED`                 | Task đã bị hủy                               |
| `OFFLINE_SYNC_CONFLICT`          | Xung đột khi đồng bộ dữ liệu offline         |
| `RATE_LIMIT_EXCEEDED`            | Vượt giới hạn thao tác                       |
| `SYSTEM_ERROR`                   | Lỗi hệ thống                                 |

---

# 29. Dữ liệu chính

## Bảng `housekeeping_tasks`

| Trường                 | Kiểu dữ liệu       | Mô tả                  |
| ---------------------- | ------------------ | ---------------------- |
| `id`                   | UUID               | Mã task                |
| `branch_id`            | UUID               | Chi nhánh              |
| `room_id`              | UUID               | Phòng                  |
| `booking_id`           | UUID, nullable     | Booking liên quan      |
| `task_type`            | VARCHAR            | Loại task              |
| `priority`             | VARCHAR            | Mức ưu tiên            |
| `status`               | VARCHAR            | Trạng thái             |
| `assignee_id`          | UUID, nullable     | Người thực hiện        |
| `shift_id`             | UUID, nullable     | Ca làm                 |
| `checklist_version_id` | UUID               | Phiên bản checklist    |
| `scheduled_start_at`   | DATETIME           | Giờ dự kiến bắt đầu    |
| `due_at`               | DATETIME           | Hạn hoàn thành         |
| `accepted_at`          | DATETIME, nullable | Thời điểm nhận         |
| `started_at`           | DATETIME, nullable | Thời điểm bắt đầu      |
| `completed_at`         | DATETIME, nullable | Thời điểm hoàn thành   |
| `progress_percent`     | DECIMAL            | Phần trăm tiến độ      |
| `pause_reason`         | VARCHAR, nullable  | Lý do tạm dừng         |
| `rework_count`         | INT                | Số lần làm lại         |
| `is_overdue`           | BOOLEAN            | Cờ quá hạn             |
| `version`              | INT                | Phiên bản khóa dữ liệu |
| `created_by`           | UUID               | Người/hệ thống tạo     |
| `created_at`           | DATETIME           | Thời gian tạo          |
| `updated_at`           | DATETIME           | Thời gian cập nhật     |

## Bảng `housekeeping_task_checklist_items`

| Trường                         | Kiểu dữ liệu       | Mô tả                |
| ------------------------------ | ------------------ | -------------------- |
| `id`                           | UUID               | Mã mục checklist     |
| `task_id`                      | UUID               | Task                 |
| `checklist_item_definition_id` | UUID               | Mục checklist gốc    |
| `title`                        | VARCHAR            | Nội dung hiển thị    |
| `item_type`                    | VARCHAR            | Loại dữ liệu         |
| `is_required`                  | BOOLEAN            | Bắt buộc             |
| `status`                       | VARCHAR            | Trạng thái xử lý     |
| `value`                        | JSON               | Giá trị đã nhập      |
| `note`                         | TEXT               | Ghi chú              |
| `completed_by`                 | UUID, nullable     | Người hoàn thành     |
| `completed_at`                 | DATETIME, nullable | Thời gian hoàn thành |

## Bảng `task_status_history`

| Trường        | Kiểu dữ liệu      | Mô tả          |
| ------------- | ----------------- | -------------- |
| `id`          | UUID              | Mã lịch sử     |
| `task_id`     | UUID              | Task           |
| `from_status` | VARCHAR           | Trạng thái cũ  |
| `to_status`   | VARCHAR           | Trạng thái mới |
| `reason_code` | VARCHAR, nullable | Lý do          |
| `note`        | TEXT, nullable    | Ghi chú        |
| `changed_by`  | UUID              | Người thay đổi |
| `changed_at`  | DATETIME          | Thời gian      |

---

# 30. Activity Log

Hệ thống phải ghi log cho các sự kiện:

* `TASK_VIEWED`
* `TASK_ACCEPTED`
* `TASK_REJECTED`
* `TASK_RETURNED`
* `TASK_STARTED`
* `TASK_PAUSED`
* `TASK_RESUMED`
* `TASK_PROGRESS_UPDATED`
* `CHECKLIST_ITEM_UPDATED`
* `PHOTO_ADDED`
* `SUPPLY_REQUEST_CREATED`
* `ISSUE_REPORTED`
* `TASK_COMPLETED`
* `TASK_SENT_TO_QC`
* `TASK_QC_REJECTED`
* `TASK_REWORK_STARTED`
* `TASK_CANCELLED`
* `TASK_REASSIGNED`

Log phải lưu:

* Task ID.
* User ID.
* Chi nhánh.
* Hành động.
* Trạng thái trước.
* Trạng thái sau.
* Thời gian.
* IP.
* Device ID.
* Dữ liệu thay đổi trước/sau khi phù hợp.

---

# 31. Quy tắc làm việc ngoại tuyến

Khi mất mạng, Quản gia có thể:

* Xem các task đã tải trước.
* Xem thông tin phòng cần thiết.
* Tick checklist.
* Ghi chú.
* Chụp ảnh.
* Tạm lưu báo cáo sự cố.

Hệ thống phải:

* Lưu dữ liệu cục bộ có mã hóa.
* Đánh dấu thao tác chờ đồng bộ.
* Hiển thị rõ trạng thái chưa đồng bộ.
* Tự đồng bộ khi có mạng.
* Không tạo checklist hoặc ảnh trùng.
* Xử lý xung đột theo version của task.
* Không cho hoàn thành cuối cùng nếu có dữ liệu bắt buộc chưa đồng bộ, trừ khi chính sách hệ thống cho phép.

---

# 32. Acceptance Criteria

## AC-01

Quản gia chỉ xem được task thuộc chi nhánh được phân quyền.

## AC-02

Mặc định danh sách hiển thị task thuộc ngày và ca hiện tại.

## AC-03

Người dùng có thể lọc task theo chi nhánh, ca, trạng thái, loại task và mức ưu tiên.

## AC-04

Task sắp quá hạn hoặc quá hạn phải được hiển thị cảnh báo rõ ràng.

## AC-05

Chỉ một nhân viên được nhận một task tại cùng thời điểm.

## AC-06

Nếu hai người nhận cùng lúc, chỉ một yêu cầu thành công.

## AC-07

Quản gia không được nhận task ngoài chi nhánh được phân quyền.

## AC-08

Quản gia không được nhận task ngoài ca, trừ khi được cấp quyền.

## AC-09

Khi nhận việc thành công, task phải gắn đúng người nhận và thời gian nhận.

## AC-10

Khi bắt đầu task, trạng thái task chuyển sang `IN_PROGRESS`.

## AC-11

Khi bắt đầu dọn, trạng thái phòng chuyển sang `CLEANING`.

## AC-12

Tiến độ phải tự động cập nhật dựa trên checklist bắt buộc đã hoàn thành.

## AC-13

Mỗi lần cập nhật checklist phải ghi người thực hiện và thời gian.

## AC-14

Không được hoàn thành task nếu còn checklist bắt buộc chưa xử lý.

## AC-15

Không được hoàn thành task nếu thiếu ảnh bắt buộc.

## AC-16

Nếu phát hiện sự cố chặn phòng, task không được làm phòng chuyển sang `READY`.

## AC-17

Khi báo sự cố, ticket phải liên kết đúng task và phòng.

## AC-18

Khi báo thiếu vật tư, yêu cầu phải được gửi đúng chi nhánh hoặc kho phụ trách.

## AC-19

Quản gia có thể tạm dừng task và phải chọn lý do.

## AC-20

Thời gian tạm dừng phải được lưu riêng để tính SLA theo cấu hình.

## AC-21

Khi hoàn thành task có yêu cầu QC, trạng thái task chuyển sang `WAITING_QC`.

## AC-22

Phòng chỉ chuyển sang `READY` sau khi QC đạt, trừ task không yêu cầu QC.

## AC-23

Khi QC không đạt, Quản gia phải thấy rõ lý do và các hạng mục cần làm lại.

## AC-24

Dữ liệu của lần QC cũ không được ghi đè khi gửi QC lại.

## AC-25

Tất cả lần nhận việc, bắt đầu, tạm dừng, hoàn thành và làm lại phải có Activity Log.

## AC-26

Danh sách task phải phản ánh cập nhật tiến độ gần thời gian thực.

## AC-27

Khi mất mạng, checklist và ảnh đã thực hiện không bị mất.

## AC-28

Khi đồng bộ lại, hệ thống không tạo dữ liệu trùng.

## AC-29

Nếu task bị cập nhật bởi người khác, hệ thống phải phát hiện xung đột phiên bản.

## AC-30

Người dùng không được sửa thủ công thời gian nhận, bắt đầu hoặc hoàn thành do hệ thống ghi nhận.

---

# 33. Test case chính

## TC-01: Xem task đúng chi nhánh

Điều kiện:

Quản gia được cấp chi nhánh A.

Kết quả mong đợi:

* Chỉ thấy task chi nhánh A.
* Không thấy task chi nhánh B.

## TC-02: Xem task theo ca

Điều kiện:

Người dùng đang ở ca sáng.

Kết quả mong đợi:

* Danh sách mặc định hiển thị task ca sáng.
* Có thể xem ca khác nếu được cấp quyền.

## TC-03: Nhận task thành công

Kết quả mong đợi:

* Task chuyển sang `ACCEPTED`.
* Gắn đúng người nhận.
* Ghi thời điểm nhận.
* Có Activity Log.

## TC-04: Hai người nhận cùng task

Kết quả mong đợi:

* Chỉ một người nhận thành công.
* Người còn lại nhận thông báo task đã được nhận.

## TC-05: Nhận task ngoài chi nhánh

Kết quả mong đợi:

* Backend từ chối.
* Trả lỗi `USER_BRANCH_NOT_ALLOWED`.

## TC-06: Bắt đầu task

Kết quả mong đợi:

* Task chuyển sang `IN_PROGRESS`.
* Phòng chuyển sang `CLEANING`.
* Ghi thời gian bắt đầu.

## TC-07: Cập nhật checklist

Kết quả mong đợi:

* Lưu trạng thái checklist.
* Tăng tiến độ task.
* Ghi người và thời gian cập nhật.

## TC-08: Hoàn thành khi thiếu checklist

Kết quả mong đợi:

* Không cho hoàn thành.
* Trả danh sách checklist bắt buộc còn thiếu.

## TC-09: Hoàn thành khi thiếu ảnh

Kết quả mong đợi:

* Không cho hoàn thành.
* Trả lỗi `REQUIRED_PHOTO_MISSING`.

## TC-10: Báo thiếu vật tư

Kết quả mong đợi:

* Tạo yêu cầu cấp vật tư.
* Thông báo cho bộ phận kho.
* Liên kết đúng task và phòng.

## TC-11: Báo thiết bị hỏng

Kết quả mong đợi:

* Tạo ticket.
* Ticket liên kết đúng phòng, task và thiết bị.
* Nếu lỗi chặn, không cho phòng chuyển sang Ready.

## TC-12: Tạm dừng task

Kết quả mong đợi:

* Lưu lý do.
* Chuyển trạng thái phù hợp.
* Ghi thời gian tạm dừng.

## TC-13: Hoàn thành và gửi QC

Kết quả mong đợi:

* Task chuyển sang `WAITING_QC`.
* Phòng chuyển sang `WAITING_QC`.
* Tạo QC task.
* QC nhận thông báo.

## TC-14: QC từ chối

Kết quả mong đợi:

* Task chuyển sang `QC_REJECTED`.
* Quản gia thấy lý do và ảnh QC.
* Phòng chuyển sang `REWORK_REQUIRED`.

## TC-15: Làm lại và gửi QC lần hai

Kết quả mong đợi:

* Lưu dữ liệu lần làm lại.
* Không ghi đè kết quả QC lần đầu.
* Tăng `rework_count`.

## TC-16: Làm việc ngoại tuyến

Kết quả mong đợi:

* Tick checklist và chụp ảnh khi mất mạng.
* Dữ liệu được giữ trên thiết bị.
* Đồng bộ khi có mạng.

## TC-17: Xung đột dữ liệu offline

Kết quả mong đợi:

* Phát hiện version không khớp.
* Không tự ghi đè dữ liệu mới hơn.
* Yêu cầu người dùng hoặc hệ thống xử lý xung đột.

## TC-18: Task quá hạn

Kết quả mong đợi:

* Task có cảnh báo quá hạn.
* Thông báo theo escalation rule.
* Dashboard ghi nhận SLA không đạt.
