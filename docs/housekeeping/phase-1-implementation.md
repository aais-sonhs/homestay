# Housekeeping — Kết quả Giai đoạn 1

> Hoàn tất: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

Schema Housekeeping đã được mở rộng theo hướng additive, không xóa/rename bảng hoặc trường MVP. Dữ liệu legacy được backfill sang domain mới qua migration riêng và vẫn giữ các field tương thích như `booking_code`, `checklist_version`, `Room.area` và `TaskPhoto.synced`.

Các domain đã bổ sung:

- Scope: Area, Team, Skill, membership role, shift assignment và branch policy.
- Room/booking: booking thật, room verification metadata và trạng thái vận hành.
- Assignment: lịch sử assignment, handover, assigned-by.
- Checklist: template, published version, item definition và task snapshot.
- Media/support: metadata ảnh, supply destination, issue resolution.
- QC/rework: QC snapshot, failed item và rework round.
- SLA: policy, task SLA state và escalation event.
- Notification: notification, recipient và transactional outbox.
- Offline: mutation receipt có unique idempotency key theo user.

## Migration

1. `0002_domain_foundation`: tạo model/index/constraint mới và field nullable/default an toàn.
2. `0003_backfill_domain_foundation`: backfill Area, membership/team, Booking, checklist version/definition, assignment, photo metadata, supply destination, QC snapshot/rework và SLA state.

Backfill được thiết kế idempotent và có reverse function để phục vụ migration test. Không phát notification/escalation lịch sử; SLA state backfill được đánh dấu `legacy_backfill=True`.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Legacy migration test | Pass `0001 → 0003`, kiểm tra quan hệ và dữ liệu |
| Domain constraints/snapshot | Pass |
| Seed domain foundation | Pass |
| Toàn bộ test | 37/37 pass trong 19,359 giây |

Chưa chạy migration lên PostgreSQL local trong Giai đoạn này để tránh tác động dữ liệu khi chưa có migration rehearsal/backup ở Giai đoạn 9.
