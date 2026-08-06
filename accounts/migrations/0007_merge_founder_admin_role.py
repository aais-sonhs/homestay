from django.db import migrations, models


def merge_admin_into_founder(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="admin").update(role="founder")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0006_alter_activitylog_event_type_and_more"),
    ]

    operations = [
        migrations.RunPython(merge_admin_into_founder, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("founder", "Nhà sáng lập / Quản trị viên"),
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
