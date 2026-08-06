from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0006_housekeepingtask_required_skills"),
    ]

    operations = [
        migrations.AlterField(
            model_name="branchmembership",
            name="membership_role",
            field=models.CharField(
                choices=[
                    ("HOUSEKEEPER", "Nhân viên buồng phòng"),
                    ("HOUSEKEEPING_LEAD", "Trưởng nhóm buồng phòng"),
                    ("MANAGER", "Quản lý"),
                    ("QC", "Kiểm tra chất lượng"),
                    ("WAREHOUSE", "Kho"),
                    ("TECHNICIAN", "Kỹ thuật"),
                    ("VIEWER", "Chỉ xem"),
                ],
                db_index=True,
                default="HOUSEKEEPER",
                max_length=24,
            ),
        ),
        migrations.AlterField(
            model_name="housekeepingtask",
            name="status",
            field=models.CharField(
                choices=[
                    ("UNASSIGNED", "Chờ phân công"),
                    ("ASSIGNED", "Đã phân công"),
                    ("PENDING_ACCEPTANCE", "Chờ nhận việc"),
                    ("ACCEPTED", "Đã nhận việc"),
                    ("IN_PROGRESS", "Đang thực hiện"),
                    ("PAUSED", "Tạm dừng"),
                    ("WAITING_SUPPORT", "Chờ hỗ trợ"),
                    ("COMPLETED", "Đã hoàn thành"),
                    ("WAITING_QC", "Chờ kiểm tra chất lượng"),
                    ("QC_REJECTED", "Kiểm tra không đạt"),
                    ("QC_APPROVED", "Kiểm tra đạt"),
                    ("CANCELLED", "Đã hủy"),
                ],
                db_index=True,
                default="UNASSIGNED",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="housekeepingtask",
            name="task_type",
            field=models.CharField(
                choices=[
                    ("CHECKOUT_CLEANING", "Dọn phòng sau khi khách trả phòng"),
                    ("STAYOVER_CLEANING", "Dọn phòng đang có khách"),
                    ("CHECKIN_PREPARATION", "Chuẩn bị phòng đón khách"),
                    ("DEEP_CLEANING", "Vệ sinh chuyên sâu"),
                    ("QC_REWORK", "Dọn lại sau kiểm tra chất lượng"),
                    ("PERIODIC_CLEANING", "Vệ sinh định kỳ"),
                ],
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="qctask",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Chờ kiểm tra chất lượng"),
                    ("APPROVED", "Đạt"),
                    ("REJECTED", "Không đạt"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="reworkround",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Chờ làm lại"),
                    ("IN_PROGRESS", "Đang làm lại"),
                    ("SENT_TO_QC", "Đã gửi kiểm tra chất lượng"),
                    ("COMPLETED", "Hoàn tất"),
                    ("CANCELLED", "Đã hủy"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="room",
            name="status",
            field=models.CharField(
                choices=[
                    ("READY", "Sẵn sàng"),
                    ("DIRTY", "Bẩn"),
                    ("WAITING_CLEANING", "Chờ dọn"),
                    ("CLEANING", "Đang dọn"),
                    ("CLEANING_BLOCKED", "Dọn phòng bị chặn"),
                    ("WAITING_QC", "Chờ kiểm tra chất lượng"),
                    ("REWORK_REQUIRED", "Cần làm lại"),
                    ("OUT_OF_SERVICE", "Ngừng phục vụ"),
                ],
                db_index=True,
                default="READY",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="taskchecklistitem",
            name="item_type",
            field=models.CharField(
                choices=[
                    ("CHECKBOX", "Ô đánh dấu"),
                    ("YES_NO", "Có/không"),
                    ("NUMBER", "Số lượng"),
                    ("TEXT", "Văn bản"),
                    ("PHOTO", "Chụp ảnh"),
                    ("SINGLE_SELECT", "Chọn một"),
                    ("MULTI_SELECT", "Chọn nhiều"),
                    ("DEVICE_CHECK", "Kiểm tra thiết bị"),
                    ("QR_SCAN", "Quét mã QR"),
                ],
                default="CHECKBOX",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="taskphoto",
            name="category",
            field=models.CharField(
                choices=[
                    ("BEFORE", "Trước khi dọn"),
                    ("AFTER", "Sau khi dọn"),
                    ("ISSUE", "Sự cố"),
                    ("SUPPLY", "Thiếu vật tư"),
                    ("QC", "Kiểm tra chất lượng"),
                    ("AREA", "Khu vực"),
                    ("EVIDENCE", "Bằng chứng hoàn thành"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="taskphoto",
            name="source",
            field=models.CharField(
                choices=[
                    ("CAMERA", "Máy ảnh"),
                    ("GALLERY", "Thư viện"),
                    ("OFFLINE_CAMERA", "Máy ảnh ngoại tuyến"),
                ],
                default="CAMERA",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="taskroomverification",
            name="method",
            field=models.CharField(
                choices=[
                    ("QR_CODE", "QR phòng"),
                    ("GPS", "GPS"),
                    ("WIFI", "Wi-Fi"),
                    ("CAMERA", "Ảnh chụp trực tiếp"),
                    ("MANAGER_OVERRIDE", "Quản lý xác nhận"),
                    ("GUEST_CONSENT", "Khách đồng ý"),
                ],
                max_length=30,
            ),
        ),
    ]
