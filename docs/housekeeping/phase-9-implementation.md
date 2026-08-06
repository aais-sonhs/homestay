# Housekeeping — Kết quả Giai đoạn 9

> Hoàn tất phạm vi code/test/migration: 05/08/2026 — Asia/Ho_Chi_Minh
> Android build và physical-device E2E: hoãn theo yêu cầu người dùng.

## Thay đổi hoàn tất

- `AC-26`: Flutter tự lấy lại danh sách mỗi 30 giây khi online; backoffice task list và operations dashboard tự làm mới khi tab đang hiển thị và người dùng không sửa form.
- Response tiến độ được kiểm chứng gồm `progressPercent`, `lastProgressAt`, `updatedBy` và `version` mới.
- PostgreSQL concurrency bao phủ cả TC-04 (hai người nhận cùng task) và AC-11/TC-06 (hai task bắt đầu cùng phòng).
- Migration `0005` có test tiến hóa từ `0004`, xác nhận receipt, request/response payload và status cũ không bị mất.
- Regression login, token rotation/logout và toàn bộ luồng quên mật khẩu được chạy lại.
- Regression tiếp nối với Flutter 3.41.9 đã sửa `LinearProgressIndicator.semanticsValue` từ chuỗi có ký hiệu `%` sang chuỗi số hợp lệ; task card vẫn đọc rõ đơn vị qua semantic label bao ngoài và widget test đã khóa giá trị này.
- Chrome audit đăng nhập thật bằng `admin` trên desktop/mobile đã sửa responsive navigation, đủ 7 tab backoffice, lọc ca và ngày mặc định, form label/accessibility, dashboard status/time/duration, favicon và confirm cho thao tác phá hủy. Selenium kiểm tra lại toàn bộ Task/Detail/Điều phối/Hỗ trợ/Activity/Thông báo không còn control thiếu nhãn, horizontal overflow toàn trang hoặc browser console error.
- `#nav-panel` giữ focus trong menu tại mục `aria-current` sau khi mở; Escape đóng menu và trả focus về `#nav-toggle`. Route hiện tại có selected state trực quan và regression test.

## Kết quả kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Django suite SQLite | 100 test: 98 pass, 2 PostgreSQL-only skip |
| PostgreSQL row-lock concurrency | 2/2 pass trên `test_homestay` |
| Accounts + token auth regression | 19/19 pass |
| Flutter analyze | Pass, 0 issue |
| Flutter unit/widget | 9/9 pass |
| `startup.sh` syntax | Pass |
| Android build | Không chạy theo yêu cầu người dùng |

## Migration PostgreSQL hiện hữu

Trước khi migrate đã tạo custom-format backup đọc được:

- `/tmp/homestay-pre-phase9-20260805.dump`
- PostgreSQL 14.23, 121 KB tại thời điểm tạo.

Đã áp dụng thành công `housekeeping.0002_domain_foundation` đến `0005_offline_sync_receipt_state`. Smoke test sau migration cho kết quả:

- 8 user, 2 branch, 6 room và 6 task — giữ nguyên số lượng trước migration.
- 6 `TaskSLAState` và 2 `BranchHousekeepingPolicy` được backfill.
- Cả 5 Housekeeping migration đều ở trạng thái applied.

File backup nằm trong `/tmp`, nên cần sao chép sang nơi lưu trữ lâu dài trước khi hệ điều hành dọn thư mục tạm nếu muốn giữ lâu dài.

## AC/TC và phạm vi hoãn

- `AC-01`–`AC-30` đều có code và test dẫn chiếu trong `requirements-traceability.md`; `AC-26` không còn trạng thái “Một phần”.
- `TC-01`–`TC-18` đều có coverage backend/API/unit/widget. Hành vi server của TC-16/TC-17 có integration test batch/replay/conflict; physical-device kill/restart/reconnect chưa chạy vì Android đang được hoãn.
- Không production deploy. Người dùng đã tự bật Homestay bằng Uvicorn tại `8020` và chỉ cho phép Codex truy cập kiểm thử; Codex không quản lý tiến trình này. Cấu hình vẫn là local development và cần domain/TLS/production settings trước khi coi là production.
- Source UI mới đã pass trên server kiểm thử sạch `18020`. Browser audit trực tiếp `8020` cho thấy worker chạy trước thay đổi còn phục vụ source/template cũ không đồng nhất; người dùng cần restart dịch vụ rồi smoke test lại để đưa bản sửa lên runtime.
- `python manage.py check --deploy` còn 5 cảnh báo đúng với local settings: HSTS, SSL redirect, secure session cookie, secure CSRF cookie và `DEBUG=True`. Cần domain/TLS/cổng được chốt trước khi tạo production settings.
