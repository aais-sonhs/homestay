import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("housekeeping", "0014_structured_booking_requests"),
    ]

    operations = [
        migrations.CreateModel(
            name="GuestServiceRequest",
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
                ("code", models.CharField(max_length=30, unique=True)),
                (
                    "request_type",
                    models.CharField(
                        choices=[
                            ("WATER", "Nước uống"),
                            ("TOWEL", "Khăn"),
                            ("AMENITY", "Đồ dùng trong phòng"),
                            ("HOUSEKEEPING", "Dọn phòng theo yêu cầu"),
                            ("MAINTENANCE", "Hỗ trợ thiết bị"),
                            ("OTHER", "Yêu cầu khác"),
                        ],
                        db_index=True,
                        max_length=24,
                    ),
                ),
                ("description", models.CharField(max_length=500)),
                ("quantity", models.PositiveSmallIntegerField(default=1)),
                ("unit", models.CharField(blank=True, max_length=30)),
                (
                    "source",
                    models.CharField(
                        choices=[
                            ("ZALO", "Zalo"),
                            ("PHONE", "Điện thoại"),
                            ("FRONT_DESK", "Lễ tân"),
                            ("OTHER", "Kênh khác"),
                        ],
                        db_index=True,
                        default="ZALO",
                        max_length=20,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[
                            ("LOW", "Thấp"),
                            ("NORMAL", "Bình thường"),
                            ("HIGH", "Cao"),
                            ("URGENT", "Khẩn cấp"),
                        ],
                        db_index=True,
                        default="NORMAL",
                        max_length=10,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("NEW", "Chờ tiếp nhận"),
                            ("ASSIGNED", "Đã phân công"),
                            ("ACCEPTED", "Đã nhận việc"),
                            ("IN_PROGRESS", "Đang thực hiện"),
                            ("COMPLETED", "Đã giao khách"),
                            ("CANCELLED", "Đã hủy"),
                        ],
                        db_index=True,
                        default="NEW",
                        max_length=20,
                    ),
                ),
                ("due_at", models.DateTimeField(db_index=True)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("cancellation_reason", models.TextField(blank=True)),
                ("resolution_note", models.TextField(blank=True)),
                ("version", models.PositiveIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "assignee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assigned_guest_service_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="dispatched_guest_service_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guest_service_requests",
                        to="housekeeping.booking",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guest_service_requests",
                        to="housekeeping.branch",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_guest_service_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="guest_service_requests",
                        to="housekeeping.room",
                    ),
                ),
            ],
            options={
                "db_table": "housekeeping_guest_service_requests",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="GuestServiceRequestEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("action", models.CharField(db_index=True, max_length=40)),
                ("from_status", models.CharField(blank=True, max_length=20)),
                ("to_status", models.CharField(blank=True, max_length=20)),
                ("note", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "request",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="housekeeping.guestservicerequest",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "housekeeping_guest_service_request_events",
                "ordering": ["created_at", "id"],
            },
        ),
        migrations.AddIndex(
            model_name="guestservicerequest",
            index=models.Index(
                fields=["branch", "status", "due_at"],
                name="hk_guest_req_queue_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="guestservicerequest",
            index=models.Index(
                fields=["assignee", "status"],
                name="hk_guest_req_worker_idx",
            ),
        ),
    ]
