# Dữ liệu demo vận hành

## Chạy seed

```bash
python manage.py migrate
python manage.py seed_operations_demo_data --reset-passwords
```

Command tự bảo đảm tài khoản, chi nhánh và dữ liệu Housekeeping nền tảng trước khi tạo
các mã `DEMO-*`. Có thể chạy lại mà không nhân bản scenario. Mật khẩu mặc định của
10 tài khoản demo là `Demo@2026Safe`.

## Scenario chính

- 11 phòng mới bao phủ: sẵn sàng, đang có khách, chưa sẵn sàng, rủi ro check-in,
  blocker đang hoạt động, chờ gỡ blocker, lịch dừng bán tương lai, chờ xác nhận mở
  lại, đã mở lại và phòng bị quản lý khóa.
- 6 booking bao phủ `BOOKED`, `CHECKED_IN`, `CHECKED_OUT`, `CANCELLED`, booking bị
  stop-sell ảnh hưởng và booking tương lai.
- Booking `DEMO-BK-CHECKIN-TODAY` có đủ bảy loại yêu cầu đặc biệt, bốn pha áp dụng,
  hai mức ưu tiên và quantity; task check-in/checkout nhận snapshot đúng pha.
- 14 task liên quan bao phủ chờ phân công, đang thực hiện, tạm dừng, chờ vật tư,
  hoàn thành, QC đạt và hủy.
- Hai IssueTicket gồm sự cố đang chặn phòng và sự cố đã xử lý đang chờ vận hành gỡ
  blocker; có yêu cầu vật tư, notification và bốn ảnh SVG minh họa.
- Năm stop-sell bao phủ: đang hiệu lực, lên lịch tương lai, chờ xác nhận mở lại,
  đã mở lại và đã hủy lịch. History và Outbox được tạo qua service nghiệp vụ.

Mở Lịch vận hành ở ngày hiện tại, sau đó xem `Trạng thái phòng`, `Booking`,
`Dừng bán phòng` và hồ sơ từng phòng. Có thể lọc/tìm kiếm bằng tiền tố `DEMO`.

## Lưu ý deploy production

Phải đồng bộ nguyên repo, không chỉ copy `reservations/` hoặc `room_operations/`.
Settings được deploy phải chứa:

```python
INSTALLED_APPS = [
    # ...
    "reservations.apps.ReservationsConfig",
    "room_operations.apps.RoomOperationsConfig",
]
```

Trước khi restart worker, chạy `python manage.py check` và `python manage.py migrate`
bằng đúng virtual environment, working directory và settings module của service.
