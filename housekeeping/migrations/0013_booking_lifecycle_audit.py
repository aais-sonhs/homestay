from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("housekeeping", "0012_sales_booking_automation"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="cancellation_reason",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancelled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="booking",
            name="cancelled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cancelled_bookings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="updated_bookings",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="version",
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name="BookingChangeLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CREATED", "Tạo booking"),
                            ("CHANGED", "Thay đổi booking"),
                            ("CANCELLED", "Hủy booking"),
                        ],
                        db_index=True,
                        max_length=20,
                    ),
                ),
                ("booking_version", models.PositiveIntegerField()),
                ("reason", models.TextField(blank=True)),
                ("before_snapshot", models.JSONField(blank=True, default=dict)),
                ("after_snapshot", models.JSONField(blank=True, default=dict)),
                ("correlation_id", models.CharField(blank=True, db_index=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="change_logs",
                        to="housekeeping.booking",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="booking_change_logs",
                        to="housekeeping.branch",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="booking_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "housekeeping_booking_change_logs",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="bookingchangelog",
            constraint=models.UniqueConstraint(
                fields=("booking", "booking_version", "action"),
                name="unique_booking_version_action",
            ),
        ),
    ]
