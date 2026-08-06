from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_user_avatar"),
    ]

    operations = [
        migrations.AlterField(
            model_name="activitylog",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("PASSWORD_RESET_REQUESTED", "Yêu cầu đặt lại mật khẩu"),
                    ("PASSWORD_RESET_OTP_VERIFIED", "Đã xác thực mã"),
                    ("PASSWORD_RESET_COMPLETED", "Hoàn tất đặt lại mật khẩu"),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="passwordresetrequest",
            name="channel",
            field=models.CharField(
                choices=[("email", "Thư điện tử"), ("sms", "SMS")],
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("founder", "Nhà sáng lập"),
                    ("admin", "Quản trị viên"),
                    ("manager", "Quản lý"),
                    ("housekeeping", "Nhân viên buồng phòng"),
                    ("qc", "Kiểm tra chất lượng"),
                    ("technician", "Kỹ thuật"),
                    ("warehouse", "Kho"),
                    ("customer_service", "CSKH"),
                ],
                default="housekeeping",
                max_length=32,
            ),
        ),
    ]
