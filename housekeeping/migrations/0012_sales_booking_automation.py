from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0010_add_sales_role"),
        ("housekeeping", "0011_enforce_branch_owner_and_history"),
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
                    ("SALES", "Kinh doanh"),
                    ("VIEWER", "Chỉ xem"),
                ],
                db_index=True,
                default="HOUSEKEEPER",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="created_bookings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="source",
            field=models.CharField(
                choices=[
                    ("MANUAL_SALES", "Nhân viên kinh doanh nhập"),
                    ("IMPORT", "Nhập từ tệp"),
                    ("PMS", "Đồng bộ PMS"),
                    ("LEGACY", "Dữ liệu cũ"),
                ],
                db_index=True,
                default="LEGACY",
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="booking",
            name="source",
            field=models.CharField(
                choices=[
                    ("MANUAL_SALES", "Nhân viên kinh doanh nhập"),
                    ("IMPORT", "Nhập từ tệp"),
                    ("PMS", "Đồng bộ PMS"),
                    ("LEGACY", "Dữ liệu cũ"),
                ],
                db_index=True,
                default="MANUAL_SALES",
                max_length=20,
            ),
        ),
    ]
