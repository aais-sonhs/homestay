from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0005_offline_sync_receipt_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="housekeepingtask",
            name="required_skills",
            field=models.ManyToManyField(
                blank=True,
                related_name="required_by_tasks",
                to="housekeeping.skill",
            ),
        ),
    ]
