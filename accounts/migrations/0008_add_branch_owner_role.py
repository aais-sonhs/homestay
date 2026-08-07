from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0007_merge_founder_admin_role"),
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
                ],
                default="housekeeping",
                max_length=32,
            ),
        ),
    ]
