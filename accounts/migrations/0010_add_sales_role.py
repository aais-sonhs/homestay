from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0009_ensure_platform_admin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("founder", "Nhà sáng lập / Quản trị viên"),
                    ("branch_owner", "Chủ chi nhánh"),
                    ("manager", "Quản lý"),
                    ("housekeeping", "Nhân viên buồng phòng"),
                    ("qc", "Kiểm tra chất lượng"),
                    ("technician", "Kỹ thuật"),
                    ("warehouse", "Kho"),
                    ("customer_service", "CSKH"),
                    ("sales", "Kinh doanh"),
                ],
                default="housekeeping",
                max_length=32,
            ),
        ),
    ]
