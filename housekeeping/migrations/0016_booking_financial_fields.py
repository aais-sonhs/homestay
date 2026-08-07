# Generated manually for Django 4.2 compatibility.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0015_guest_service_requests"),
    ]

    operations = [
        migrations.AddField(
            model_name="booking",
            name="discount_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Tổng số tiền giảm giá của booking.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="paid_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Tổng số tiền khách đã thanh toán.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="room_charge",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Tổng tiền phòng của cả kỳ lưu trú.",
                max_digits=14,
            ),
        ),
        migrations.AddField(
            model_name="booking",
            name="service_charge",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Phụ thu và dịch vụ tính thêm cho booking.",
                max_digits=14,
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(("room_charge__gte", 0))
                    & models.Q(("service_charge__gte", 0))
                    & models.Q(("discount_amount__gte", 0))
                    & models.Q(("paid_amount__gte", 0))
                ),
                name="booking_money_values_nonneg",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                check=models.Q(
                    ("discount_amount__lte", models.F("room_charge") + models.F("service_charge"))
                ),
                name="booking_discount_within_total",
            ),
        ),
        migrations.AddConstraint(
            model_name="booking",
            constraint=models.CheckConstraint(
                check=models.Q(
                    (
                        "paid_amount__lte",
                        models.F("room_charge")
                        + models.F("service_charge")
                        - models.F("discount_amount"),
                    )
                ),
                name="booking_paid_within_total",
            ),
        ),
    ]
