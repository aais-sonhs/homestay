# Housekeeping — Kết quả Giai đoạn 2

> Hoàn tất: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

Permission, query scope, state transition và concurrency đã được tách thành các lớp tập trung. Service không còn tự quyết định quyền hoặc chuyển trạng thái bằng các nhánh rời rạc.

Các thành phần chính:

- `permissions.py`: quyền theo global role, membership role, chi nhánh, khu vực, team, ca và ngoại lệ ngoài ca.
- `selectors.py`: chỉ trả task trong scope; ưu tiên QC rework, check-in gần, quá hạn, khẩn cấp, được giao và deadline.
- `state_machine.py`: bảng action/transition duy nhất, status history, activity log, optimistic version và đồng bộ trạng thái phòng.
- `idempotency.py`: khóa idempotency theo user/key, hash payload, replay kết quả thành công và từ chối tái sử dụng key sai payload.
- `services.py`: transaction/row lock cho accept, start, checklist, media, pause/resume, supply, issue, complete, QC, phân công lại, hủy và đổi ưu tiên.

## Quy tắc đã bảo vệ

- Housekeeper chỉ xem/nhận task đúng branch, area, team và shift; manager/QC/lead theo đúng scope.
- Chỉ một trong hai yêu cầu nhận task đồng thời thành công.
- Không có hai task active cùng xử lý một phòng nếu branch policy không cho phép.
- Bắt đầu task hỗ trợ bắt buộc QR và xác nhận khách đồng ý theo policy.
- Complete luôn ghi hai bước `COMPLETED` rồi `WAITING_QC`; phòng chỉ `READY` sau QC approve hoặc loại task không cần QC.
- QC reject đưa phòng sang `REWORK_REQUIRED`; rework quay lại `IN_PROGRESS` mà giữ lịch sử.
- Hủy task active tính lại trạng thái phòng và không tự chuyển phòng sang `READY`.
- Mọi mutation workflow kiểm tra version và ghi status history/activity metadata.

## PostgreSQL concurrency

Test `PostgreSQLAcceptConcurrencyTests` chạy hai thread với hai database connection độc lập. Cả hai cùng nhận một task/version; row lock đảm bảo một request thành công và request còn lại nhận `TASK_ALREADY_ASSIGNED`.

Trong lần chạy đầu, test này phát hiện PostgreSQL không cho `FOR UPDATE` trên phía nullable của `LEFT JOIN`. Truy vấn đã được sửa thành `select_for_update(of=("self",))`, chỉ khóa hàng task trong khi vẫn eager-load quan hệ. Test PostgreSQL sau sửa đạt 1/1.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Policy/state/idempotency tests | 10/10 pass |
| PostgreSQL row-lock concurrency | 1/1 pass trên database test riêng |
| SQLite fallback | Concurrency test được skip vì backend không có row lock |

Database nghiệp vụ `homestay` không bị migrate, reset hoặc ghi dữ liệu trong Giai đoạn 2. PostgreSQL test runner chỉ tạo rồi xóa `test_homestay`.
