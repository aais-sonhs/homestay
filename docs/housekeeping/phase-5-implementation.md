# Housekeeping — Kết quả Giai đoạn 5

> Hoàn tất backend/API: 05/08/2026 — Asia/Ho_Chi_Minh

## Kết quả

QC và rework đã chuyển từ reason/note đơn giản sang dữ liệu nhiều vòng bất biến.

- QC chỉ tải media khi task `WAITING_QC`, ảnh gắn đúng pending QC round và user QC.
- Reject lưu general reason/note, deadline tương lai, failed items, QC media IDs và result snapshot.
- Mỗi failed item liên kết checklist snapshot hiện tại, reason code/reason/note và cờ cần rework.
- Reject tạo một `ReworkRound`; nếu branch policy bật, chỉ các failed item được reset về pending và được phép sửa.
- Start rework cập nhật round, assignee/timestamp, task counter và room state.
- Complete rework chuyển round sang `SENT_TO_QC` và tạo QC round mới với checklist snapshot mới.
- QC approve hoàn tất rework round, kết thúc assignment và chỉ lúc đó đưa phòng `READY`.
- QC reject tiếp theo kết thúc vòng rework cũ và tạo vòng mới; dữ liệu QC cũ không bị update.
- Detail API trả deadline, result snapshot, QC media, failed items và toàn bộ rework lifecycle.

## Kiểm chứng

Integration test thực hiện đầy đủ:

1. Housekeeper complete và tạo QC round 1.
2. QC tải ảnh, reject một checklist item với deadline.
3. Hệ thống tạo failed item/rework round và giảm progress.
4. Housekeeper không sửa được item ngoài rework scope.
5. Sửa item lỗi, complete và tạo QC round 2.
6. QC approve; room `READY`, round 1 vẫn giữ nguyên snapshot/reason/media.

| Kiểm tra | Kết quả |
|---|---|
| Phase 5 multi-round integration | Pass |
| Django system check | Pass, 0 issue |
| Migration drift | Không có model change chưa tạo migration |
| Toàn bộ suite SQLite | 73 test: 72 pass, 1 concurrency skip |
| PostgreSQL row-lock concurrency | 1/1 pass trên `test_homestay` |
