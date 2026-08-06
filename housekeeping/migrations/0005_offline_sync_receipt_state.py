from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0004_execution_verification_policy"),
    ]

    operations = [
        migrations.AddField(
            model_name="offlinemutationreceipt",
            name="client_mutation_id",
            field=models.CharField(blank=True, db_index=True, max_length=80),
        ),
        migrations.AddField(
            model_name="offlinemutationreceipt",
            name="conflict_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="offlinemutationreceipt",
            name="depends_on",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="offlinemutationreceipt",
            name="resolution",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="offlinemutationreceipt",
            name="resolved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="offlinemutationreceipt",
            name="status",
            field=models.CharField(
                choices=[
                    ("RECEIVED", "Đã nhận"),
                    ("SUCCEEDED", "Thành công"),
                    ("FAILED", "Thất bại"),
                    ("CONFLICT", "Xung đột"),
                    ("DISCARDED", "Đã bỏ thay đổi cục bộ"),
                ],
                db_index=True,
                default="RECEIVED",
                max_length=20,
            ),
        ),
    ]
