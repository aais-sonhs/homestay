# Housekeeping — Requirement traceability

> Trạng thái đánh giá: **Đạt MVP** = code hiện tại đáp ứng criterion và có test tự động ở lớp phù hợp; physical-device E2E được ghi riêng khi đang hoãn. **Một phần** và **Thiếu** chỉ dùng khi còn khoảng trống code/contract bắt buộc.

## 1. Acceptance Criteria AC-01–AC-30

| AC | Hiện trạng | Bằng chứng hiện tại | Gap/đầu ra mục tiêu | Test đích |
|---|---|---|---|---|
| AC-01 | Đạt MVP | Scope tập trung branch/area/team trong `permissions.py`, `selectors.py`; Bearer và backoffice queue đều có scope test | Duy trì regression | Permission/API/Phase 8 queue |
| AC-02 | Đạt MVP | `api/query.py` default ngày và explicit `ShiftAssignment`; test roster + xem ca khác | Duy trì regression | TC-02 API |
| AC-03 | Đạt MVP | API + Flutter/backoffice có đủ 7 tab, search và filter branch/shift/area/floor/roomType/type/status/priority/assignee/overdue/check-in risk/QC rework; support/waiting-QC/done có regression riêng | Physical-device polish hoãn | API + Phase 8/10 UI test |
| AC-04 | Đạt MVP | SLA evaluator/dashboard và task card/detail có countdown, overdue/check-in text + icon + Semantics; Chrome desktop/mobile audit không còn overflow/control thiếu nhãn | Physical-device accessibility audit hoãn | SLA API + Flutter widget + browser audit |
| AC-05 | Đạt MVP | Transaction + task row lock + version + Idempotency-Key + notification | Duy trì regression | TC-03/TC-04 PostgreSQL |
| AC-06 | Đạt MVP | `test_postgres_concurrency.py` chạy hai connection/thread thật, 2/2 pass | Đưa suite PostgreSQL vào CI khi có CI | TC-04 concurrency |
| AC-07 | Đạt MVP | Bearer mutation ngoài branch trả 403 `USER_BRANCH_NOT_ALLOWED`; queue support cũng scope theo branch | Duy trì regression | TC-05 API + Phase 8 queue |
| AC-08 | Đạt MVP | ShiftAssignment, outside-shift policy và explicit roster list/accept guard | UI lập lịch overtime ngoài phạm vi criterion | Shift permission matrix |
| AC-09 | Đạt MVP | Assignment history, accepted_at/activity, idempotent replay và workflow notification | Duy trì regression | TC-03 + Phase 6 notification |
| AC-10 | Đạt MVP | Start qua state machine; Flutter lấy QR bằng scanner, GPS từ Geolocator, Wi-Fi từ thiết bị và camera BEFORE, backend đối chiếu room verification policy | Physical-device E2E hoãn | TC-06 + Phase 10 source/analyze |
| AC-11 | Đạt MVP | Room row lock, centralized room sync, parallel-room policy và PostgreSQL same-room start race 1-success/1-reject | Duy trì PostgreSQL regression | TC-06 concurrency |
| AC-12 | Đạt MVP | 9 typed validators và Flutter typed editor đủ checkbox/yes-no/number/text/photo/single/multi/device/QR; QR_SCAN chỉ nhận giá trị từ camera scanner | Device input E2E hoãn | TC-07 unit/API + widget/source contract |
| AC-13 | Đạt MVP | completed user/time, item/task version, progress activity/idempotency và poll metadata test | Duy trì regression | TC-07/TC-17/Phase 9 polling |
| AC-14 | Đạt MVP | Shared completion validator; failed reason/ticket/manager acceptance và completion summary UI | Device E2E hoãn | TC-08 + failed cases |
| AC-15 | Đạt MVP | Required count chỉ tính media `SYNCED`; checksum/direct-camera/offline encrypted BLOB policy | Physical-device media E2E hoãn | TC-09 + Phase 7 contract |
| AC-16 | Đạt MVP | Shared blocker guard cho complete/room-ready path; support và QC failed-item resolution | Duy trì regression | TC-11/TC-14 |
| AC-17 | Đạt MVP | Issue link task/room/booking/device text/media; Kỹ thuật queue/resolution và notification | Asset FK chỉ bổ sung khi có inventory module | TC-11 |
| AC-18 | Đạt MVP | Supply destination/branch/items/media; Kho queue/fulfillment và notification | Duy trì regression | TC-10 |
| AC-19 | Đạt MVP | Pause reason allow-list, required note, PAUSED/WAITING_SUPPORT và UI hành động | Duy trì regression | TC-12 |
| AC-20 | Đạt MVP | Pause interval + excluded flag/seconds; evaluator và dashboard tính active/pause/SLA duration | Duy trì regression | TC-12 + SLA duration |
| AC-21 | Đạt MVP | Complete ghi `COMPLETED` rồi `WAITING_QC`, tạo immutable QC round và notification QC/outbox | Duy trì regression | TC-13 |
| AC-22 | Đạt MVP | Central state machine chỉ READY sau QC approve/no-QC và blocker guard | Duy trì regression | TC-13/TC-14 |
| AC-23 | Đạt MVP | Failed items/QC media/reason/note/deadline API; Flutter cho QC chụp ảnh trực tiếp và detail/backoffice hiện rõ QC round/hạng mục/rework deadline | Device rework E2E hoãn | TC-14 + Phase 8/10 UI |
| AC-24 | Đạt MVP | QC/rework round unique, snapshot/result riêng; multi-round end-to-end test | Duy trì immutability regression | TC-15 |
| AC-25 | Đạt MVP | Event contract cho view/accept/start/pause/resume/complete/send QC/reject/rework/approve; manager note có activity + recipient notification | Duy trì regression | Activity event + Phase 6/10 notification |
| AC-26 | Đạt MVP | API trả progress/version/user/time mới; Flutter và backoffice poll 30 giây khi online/visible, có guard form đang sửa | Push/SSE chỉ cần nếu yêu cầu latency thấp hơn 30 giây | Phase 9 polling integration/source |
| AC-27 | Đạt MVP | Flutter dùng secure token store + SQLCipher cho cache/queue/photo BLOB; web bỏ business `localStorage`; checklist/photo giữ offline | Physical-device kill/restart E2E hoãn | TC-16 backend + Flutter source/unit |
| AC-28 | Đạt MVP | Client UUID/idempotency, dependency order, per-item receipt/replay; media receipt lưu client ID, camera START resolve server photo ID; auto-sync khi reconnect | Physical-device reconnect E2E hoãn | Phase 7 batch/replay + Phase 10 media dependency + Flutter test |
| AC-29 | Đạt MVP | Exact base version, base/local/server snapshot, không auto-rebase; Flutter có màn hình discard/retry conflict | Physical-device conflict E2E hoãn | Phase 7 conflict/resolve + widget |
| AC-30 | Đạt MVP | API serializer allow-list; timestamp nhận/bắt đầu/hoàn thành chỉ do service ghi | Duy trì schema regression | Mutation schema test |

## 2. Test Case TC-01–TC-18

| TC | Trạng thái | Bằng chứng và giới hạn kiểm chứng |
|---|---|---|
| TC-01 | Pass | Bearer list/detail scope, selector area/team và Phase 8 support/activity scope tests |
| TC-02 | Pass | Explicit roster làm ca mặc định và API filter xem ca khác |
| TC-03 | Pass | Accept ghi assignee/time/history/activity; idempotent replay và notification regression |
| TC-04 | Pass PostgreSQL | Hai connection/thread thật: 1 success, 1 `TASK_ALREADY_ASSIGNED` |
| TC-05 | Pass | Ngoài branch trả 403 `USER_BRANCH_NOT_ALLOWED`; detail ngoài scope trả 404 |
| TC-06 | Pass PostgreSQL + integration | Status/time/room state, QR/GPS/Wi-Fi/camera/guest consent và same-room start race 1-success/1-reject |
| TC-07 | Pass | Đủ 9 item type, validation/failure/progress/audit/idempotency; Phase 9 xác nhận poll thấy user/time/version mới |
| TC-08 | Pass | Shared completion summary trả danh sách checklist thiếu và failed-item resolution |
| TC-09 | Pass | Category/count/sync state/checksum/direct-camera của ảnh bắt buộc |
| TC-10 | Pass | Supply service/API, branch destination/items, queue fulfill và warehouse notification |
| TC-11 | Pass | Ticket gắn task/room/booking/device/attachment; blocker chặn complete và QC approve |
| TC-12 | Pass | Pause reason/time, WAITING_SUPPORT, blocker, SLA include/exclude và duration |
| TC-13 | Pass | COMPLETED → WAITING_QC, room state, immutable QC round và QC notification/outbox |
| TC-14 | Pass backend/UI | Failed item/reason/media/deadline, room REWORK_REQUIRED và Flutter/backoffice visibility; device E2E hoãn |
| TC-15 | Pass | Rework timestamps/scope/media, round/snapshot bất biến và rework count qua nhiều vòng |
| TC-16 | Pass backend/source/widget | Encrypted cache/queue/photo contract, dependency drain, reconnect engine; physical-device kill/restart E2E hoãn |
| TC-17 | Pass backend/widget | Base/local/server conflict, no-overwrite, explicit discard/retry, replay và three-way widget; physical-device E2E hoãn |
| TC-18 | Pass | Deadline/near-due/escalation 5/15/30 dedupe/check-in urgent/dashboard và Flutter countdown warning |

## 3. Mapping kiến trúc đích

| Requirement group | Model | Service/selector | API/UI | Test suite |
|---|---|---|---|---|
| AC-01–04 | membership/area/team/shift, SLA state | permissions, task list selector, SLA annotations | list filters/tabs/countdown | permission/list/SLA UI |
| AC-05–09, 29–30 | task, assignment, receipt | state machine, assignment service | accept/reject/return | concurrency/idempotency/schema |
| AC-10–13 | verification, checklist snapshot, media | execution/checklist/media services | start/detail/typed checklist/camera | verification/type/progress |
| AC-14–20 | pause, supply, issue | completion validator, supply/issue/pause | completion summary/support queues | blocker/SLA/integration |
| AC-21–25 | QC/rework/activity/outbox | QC state machine/notification | QC/rework screens | immutable rounds/events |
| AC-26 | task progress/outbox | scoped list/dashboard query | polling 30 giây trên Flutter/backoffice | polling integration/source |
| AC-27–29 | receipt/sync contract | sync/idempotency service | Flutter encrypted cache/queue/conflict | offline E2E/replay/conflict |

Mỗi test mới phải ghi AC/TC trong docstring hoặc tên class/module để báo cáo cuối có thể truy ngược tự động.
