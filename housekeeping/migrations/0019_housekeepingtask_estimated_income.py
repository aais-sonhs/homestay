from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("housekeeping", "0018_operatingexpense_category_code")]

    operations = [
        migrations.AddField(
            model_name="housekeepingtask",
            name="estimated_income",
            field=models.DecimalField(
                blank=True,
                decimal_places=0,
                help_text="Thu nhập dự kiến của nhân viên khi hoàn thành công việc.",
                max_digits=12,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name="housekeepingtask",
            constraint=models.CheckConstraint(
                check=models.Q(estimated_income__isnull=True)
                | models.Q(estimated_income__gte=0),
                name="hk_task_est_income_nonneg",
            ),
        ),
    ]
