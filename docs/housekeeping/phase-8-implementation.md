# Housekeeping — Kết quả Giai đoạn 8

> Hoàn tất Flutter/backoffice MVP: 05/08/2026 — Asia/Ho_Chi_Minh

## Field app

- Danh sách có 7 tab theo README, search, advanced filters và cache SQLCipher tách riêng theo view/filter.
- Task card hiển thị mã/phòng/chi nhánh/khu vực/task type/priority/status/assignee/room state/check-in/note/checklist/ảnh/sync state.
- Countdown, overdue, check-in risk, waiting support và QC rework đều có chữ + icon; widget có semantics label/live region.
- Detail gồm task/room/booking/SLA, grouped checklist, ảnh, vật tư/sự cố, ghi chú, QC/rework và timeline.
- Typed checklist editor hỗ trợ `CHECKBOX`, `YES_NO`, `NUMBER`, `TEXT`, `PHOTO`, `SINGLE_SELECT`, `MULTI_SELECT`, `DEVICE_CHECK`, `QR_SCAN`.
- Photo camera/gallery nằm trong SQLCipher BLOB với preview và sync state; evidence/photo checklist ưu tiên camera.
- Conflict sheet hiển thị base/local/server snapshot trước explicit discard/retry.
- Completion summary dùng endpoint blocker chung; local pending/failed/conflict luôn disable complete.
- Sync engine re-evaluate dependency sau mỗi vòng để drain chuỗi checklist → photo → complete trong cùng reconnect.
- Tab/cache và queue được bind với owner user UUID; app không cho logout khi còn unresolved work và secure-delete cache trước khi đổi tài khoản.

## Backoffice

- Task list có tabs và filter đầy đủ hơn; card có overdue/check-in, guest/special-request và room status.
- Operations dashboard có SLA summary, risk list, team progress, QC queue và performance theo nhân viên/ca/chi nhánh.
- Task detail có điều chuyển, đổi ưu tiên, hủy và QC reject theo failed item/deadline.
- Support queue cho Kho/Kỹ thuật dùng đúng branch scope và optimistic entity version.
- Activity Log lọc theo event/search và không vượt task scope.
- Notification Center chỉ hiển thị recipient của user và hỗ trợ đánh dấu đã đọc.

## Kiểm chứng

| Kiểm tra | Kết quả |
|---|---|
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Phase 8 backend/source UI contract | 7/7 pass |
| Toàn bộ Django suite SQLite | 93 test: 92 pass, 1 PostgreSQL-only skip |
| PostgreSQL row-lock concurrency | 1/1 pass trên `test_homestay` |
| Flutter analyze | Pass, 0 issue |
| Flutter unit/widget test | 9/9 pass |

Flutter doctor nhận Android SDK 36 nhưng môi trường hiện tại không có JDK; vì vậy chưa tuyên bố Android APK/release build pass. ADB cũng bị sandbox chặn socket/USB. Build/sign và device E2E là đầu ra Phase 9.

## Phần chuyển sang Giai đoạn 9

- Cài/cấp JDK phù hợp, chạy Android build; chạy iOS build/sign trên macOS CI.
- Device E2E: offline checklist/photo/issue, kill/restart, reconnect, conflict resolve và account isolation.
- Accessibility audit với TalkBack/VoiceOver, cỡ chữ lớn và thiết bị màn hình nhỏ.
- Đóng các gap còn “Một phần” trong traceability, regression login/forgot-password và deploy smoke test trên cổng được người dùng phê duyệt.
