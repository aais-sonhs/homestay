# Cấu trúc dự án Homestay

Homestay giữ convention cấp cao của `/mnt/data/fasthub` nhưng dùng tên miền
nghiệp vụ buồng phòng riêng.

```text
homestay/
├── accounts/          Tài khoản, đăng nhập, token và quên mật khẩu
├── common/            Access policy, API auth, display, form và list helpers
├── config/            Django settings, URL, ASGI và WSGI
├── organizations/     Chi nhánh, khu vực, phòng, ca, nhóm và membership
├── operations/        Facade theo convention Fasthub cho nghiệp vụ vận hành
├── housekeeping/      Implementation task, checklist, QC, SLA và offline sync
├── housekeeping_app/  Ứng dụng Flutter cho nhân viên hiện trường
├── static/            CSS, JavaScript và branding nguồn
├── staticfiles/       Kết quả `collectstatic`, không chỉnh trực tiếp
├── templates/         Base, shared partials và template theo ứng dụng
├── media/             File người dùng tải lên, không commit
├── scripts/           Script hỗ trợ build/kiểm tra/triển khai
├── logs/              Log ứng dụng và HTTP server
├── releases/          Artifact phát hành
└── docs/              Tài liệu kỹ thuật và nghiệp vụ
```

## Ranh giới migration hiện tại

`Branch`, `Area`, `Room`, `Shift`, `BranchMembership` và các model tổ chức đã
tồn tại trong migration `housekeeping`. `organizations.models` cung cấp đường
import chuẩn mới nhưng chưa đổi `app_label` hoặc tên bảng. Cách này giữ nguyên
dữ liệu PostgreSQL và cho phép chuyển ownership bằng một migration trạng thái
riêng ở giai đoạn sau.

Tương tự, `operations` là facade tương thích; implementation nghiệp vụ vẫn ở
`housekeeping`. Các module cũ như `housekeeping.permissions` được giữ dưới dạng
wrapper trong thời gian chuyển đổi, còn code production sử dụng `common`.

## Static files

File nguồn nằm trong `static/`, được khai báo bằng `STATICFILES_DIRS`. Lệnh
`python manage.py collectstatic --noinput` tạo output trong `staticfiles/`.
WhiteNoise phục vụ output đã nén khi Django chạy với `DEBUG=False`.

