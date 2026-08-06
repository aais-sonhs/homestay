# Housekeeping — Kết quả Giai đoạn 6

> Hoàn tất backend/API: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

- `housekeeping/sla.py` chụp SLA policy vào từng task, tính acceptance/start/completion breach, standard duration, pause excluded time và check-in risk.
- Check-in risk tự nâng priority lên `URGENT`, tạo activity log và notification; evaluator chạy lại không tạo escalation/notification trùng.
- Escalation mặc định: 5 phút tới assignee Housekeeping, 15 phút tới Housekeeping Lead, 30 phút tới Manager.
- `evaluate_housekeeping_sla` là entry point cho cron/worker; hỗ trợ branch/task/time/limit.
- Notification được tạo cùng transaction với task, supply, issue và QC; outbox dedup giữ event ổn định.
- API notification có scope theo recipient, filter unread, phân trang và mutation read idempotent.
- SLA dashboard trả near-due/overdue/check-in risk và breach; performance dashboard nhóm theo nhân viên/ca/chi nhánh.
- Duration tách elapsed, active, pause và SLA-active; rework round được đưa vào performance.

## API

- `GET /api/v1/housekeeping/notifications`
- `POST /api/v1/housekeeping/notifications/{recipientId}/read`
- `GET /api/v1/housekeeping/dashboard/sla`
- `GET /api/v1/housekeeping/dashboard/performance`

## Kiểm chứng

`test_phase6_sla_notifications.py` bao phủ:

1. Breach cả ba deadline và escalation đúng vai trò 5/15/30.
2. Dedupe khi evaluator chạy lại.
3. Check-in risk chuyển priority khẩn cấp.
4. Near-due và active/pause duration trên dashboard.
5. Performance theo employee/shift/branch.
6. Notification list/read scope + idempotency.
7. Notification nghiệp vụ tới QC, Kho và Kỹ thuật.
8. Management command đánh giá một task được chọn.
