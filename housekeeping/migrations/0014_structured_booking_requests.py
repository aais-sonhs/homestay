import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


TYPE_LABELS = {
    "BEDDING": "Giường và đồ vải",
    "AMENITY": "Tiện nghi và vật tư",
    "ARRIVAL": "Nhận phòng và đón khách",
    "ACCESSIBILITY": "Hỗ trợ tiếp cận",
    "HOUSEKEEPING": "Vệ sinh và buồng phòng",
    "CELEBRATION": "Trang trí và dịp đặc biệt",
    "OTHER": "Yêu cầu khác",
}
PHASE_LABELS = {
    "CHECKIN": "Trước khi nhận phòng",
    "STAY": "Trong thời gian lưu trú",
    "CHECKOUT": "Khi trả phòng",
    "ALL": "Toàn bộ kỳ ở",
}
PRIORITY_LABELS = {"NORMAL": "Bình thường", "HIGH": "Ưu tiên cao"}


def _snapshot(item):
    return {
        "sourceRequestId": str(item.id),
        "requestType": item.request_type,
        "requestTypeLabel": TYPE_LABELS[item.request_type],
        "appliesTo": item.applies_to,
        "appliesToLabel": PHASE_LABELS[item.applies_to],
        "priority": item.priority,
        "priorityLabel": PRIORITY_LABELS[item.priority],
        "description": item.description,
        "quantity": item.quantity,
    }


def backfill_structured_requests(apps, schema_editor):
    Booking = apps.get_model("housekeeping", "Booking")
    BookingSpecialRequest = apps.get_model("housekeeping", "BookingSpecialRequest")
    Task = apps.get_model("housekeeping", "HousekeepingTask")

    BookingSpecialRequest.objects.bulk_create(
        [
            BookingSpecialRequest(
                branch_id=booking.branch_id,
                booking_id=booking.id,
                request_type="OTHER",
                applies_to="ALL",
                priority="NORMAL",
                description=booking.special_requests.strip(),
                sort_order=0,
                created_by_id=booking.created_by_id,
            )
            for booking in Booking.objects.exclude(special_requests="").iterator()
            if booking.special_requests.strip()
        ]
    )
    requests_by_booking = {}
    for item in BookingSpecialRequest.objects.order_by("booking_id", "sort_order", "created_at", "id"):
        requests_by_booking.setdefault(item.booking_id, []).append(item)

    for task in Task.objects.all().iterator():
        items = requests_by_booking.get(task.booking_id, [])
        if task.task_type == "CHECKIN_PREPARATION":
            allowed_phases = {"CHECKIN", "STAY", "ALL"}
        elif task.task_type == "CHECKOUT_CLEANING":
            allowed_phases = {"CHECKOUT", "ALL"}
        else:
            allowed_phases = {"ALL"}
        snapshots = [_snapshot(item) for item in items if item.applies_to in allowed_phases]
        if not snapshots and task.special_request.strip():
            snapshots = [
                {
                    "sourceRequestId": None,
                    "requestType": "OTHER",
                    "requestTypeLabel": TYPE_LABELS["OTHER"],
                    "appliesTo": "ALL",
                    "appliesToLabel": PHASE_LABELS["ALL"],
                    "priority": "NORMAL",
                    "priorityLabel": PRIORITY_LABELS["NORMAL"],
                    "description": task.special_request.strip(),
                    "quantity": None,
                }
            ]
        if snapshots:
            Task.objects.filter(pk=task.pk).update(special_request_items=snapshots)


def clear_structured_task_snapshots(apps, schema_editor):
    Task = apps.get_model("housekeeping", "HousekeepingTask")
    Task.objects.update(special_request_items=[])


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("housekeeping", "0013_booking_lifecycle_audit"),
    ]

    operations = [
        migrations.AddField(
            model_name="housekeepingtask",
            name="special_request_items",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="BookingSpecialRequest",
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
                    "request_type",
                    models.CharField(
                        choices=[
                            ("BEDDING", "Giường và đồ vải"),
                            ("AMENITY", "Tiện nghi và vật tư"),
                            ("ARRIVAL", "Nhận phòng và đón khách"),
                            ("ACCESSIBILITY", "Hỗ trợ tiếp cận"),
                            ("HOUSEKEEPING", "Vệ sinh và buồng phòng"),
                            ("CELEBRATION", "Trang trí và dịp đặc biệt"),
                            ("OTHER", "Yêu cầu khác"),
                        ],
                        db_index=True,
                        default="OTHER",
                        max_length=24,
                    ),
                ),
                (
                    "applies_to",
                    models.CharField(
                        choices=[
                            ("CHECKIN", "Trước khi nhận phòng"),
                            ("STAY", "Trong thời gian lưu trú"),
                            ("CHECKOUT", "Khi trả phòng"),
                            ("ALL", "Toàn bộ kỳ ở"),
                        ],
                        db_index=True,
                        default="CHECKIN",
                        max_length=16,
                    ),
                ),
                (
                    "priority",
                    models.CharField(
                        choices=[("NORMAL", "Bình thường"), ("HIGH", "Ưu tiên cao")],
                        db_index=True,
                        default="NORMAL",
                        max_length=12,
                    ),
                ),
                ("description", models.CharField(max_length=500)),
                ("quantity", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "booking",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="special_request_items",
                        to="housekeeping.booking",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="booking_special_requests",
                        to="housekeeping.branch",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_booking_special_requests",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "housekeeping_booking_special_requests",
                "ordering": ["sort_order", "created_at", "id"],
                "indexes": [
                    models.Index(
                        fields=["branch", "booking", "applies_to"],
                        name="hk_booking_req_scope_idx",
                    )
                ],
            },
        ),
        migrations.RunPython(backfill_structured_requests, clear_structured_task_snapshots),
    ]
