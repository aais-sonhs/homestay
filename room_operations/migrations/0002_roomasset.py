import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0017_capital_and_operating_expenses"),
        ("room_operations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoomAsset",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=40)),
                ("name", models.CharField(max_length=180)),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("AIR_CONDITIONER", "Điều hòa"),
                            ("WATER_HEATER", "Bình nóng lạnh"),
                            ("REFRIGERATOR", "Tủ lạnh"),
                            ("TELEVISION", "Tivi"),
                            ("DOOR_LOCK", "Khóa cửa"),
                            ("ELECTRICAL", "Thiết bị điện"),
                            ("PLUMBING", "Cấp thoát nước"),
                            ("FIRE_SAFETY", "Phòng cháy chữa cháy"),
                            ("FURNITURE", "Nội thất"),
                            ("OTHER", "Khác"),
                        ],
                        db_index=True,
                        default="OTHER",
                        max_length=24,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPERATIONAL", "Hoạt động bình thường"),
                            ("FAULT", "Đang có sự cố"),
                            ("MAINTENANCE", "Đang bảo trì"),
                            ("OUT_OF_SERVICE", "Ngừng sử dụng"),
                        ],
                        db_index=True,
                        default="OPERATIONAL",
                        max_length=24,
                    ),
                ),
                ("serial_number", models.CharField(blank=True, max_length=100)),
                ("purchase_date", models.DateField(blank=True, null=True)),
                ("last_maintenance_at", models.DateField(blank=True, null=True)),
                ("next_maintenance_at", models.DateField(blank=True, db_index=True, null=True)),
                ("note", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="room_assets",
                        to="housekeeping.branch",
                    ),
                ),
                (
                    "room",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assets",
                        to="housekeeping.room",
                    ),
                ),
            ],
            options={
                "db_table": "room_operations_assets",
                "ordering": ["branch__name", "room__code", "code"],
            },
        ),
        migrations.AddConstraint(
            model_name="roomasset",
            constraint=models.UniqueConstraint(fields=("branch", "code"), name="unique_room_asset_branch_code"),
        ),
        migrations.AddIndex(
            model_name="roomasset",
            index=models.Index(fields=["branch", "status", "is_active"], name="room_asset_scope_status_idx"),
        ),
        migrations.AddIndex(
            model_name="roomasset",
            index=models.Index(fields=["branch", "next_maintenance_at"], name="room_asset_maintenance_idx"),
        ),
    ]
