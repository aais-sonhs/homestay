# Generated manually for Django 4.2 compatibility.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0016_booking_financial_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CapitalEntry",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=180)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("capital_date", models.DateField(db_index=True, default=timezone.localdate)),
                ("source", models.CharField(blank=True, max_length=180)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="capital_entries", to="housekeeping.branch")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_capital_entries", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_capital_entries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "housekeeping_capital_entries",
                "ordering": ["-capital_date", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OperatingExpense",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=180)),
                ("category", models.CharField(blank=True, max_length=100)),
                ("amount", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("expense_date", models.DateField(db_index=True, default=timezone.localdate)),
                ("payment_status", models.CharField(choices=[("PLANNED", "Dự kiến"), ("PAID", "Đã chi")], db_index=True, default="PAID", max_length=10)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="operating_expenses", to="housekeeping.branch")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_operating_expenses", to=settings.AUTH_USER_MODEL)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="updated_operating_expenses", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "housekeeping_operating_expenses",
                "ordering": ["-expense_date", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="capitalentry",
            constraint=models.CheckConstraint(check=models.Q(("amount__gte", 0)), name="capital_entry_amount_nonneg"),
        ),
        migrations.AddConstraint(
            model_name="operatingexpense",
            constraint=models.CheckConstraint(check=models.Q(("amount__gte", 0)), name="operating_expense_amount_nonneg"),
        ),
        migrations.AddIndex(
            model_name="capitalentry",
            index=models.Index(fields=["branch", "capital_date"], name="capital_branch_date_idx"),
        ),
        migrations.AddIndex(
            model_name="operatingexpense",
            index=models.Index(fields=["branch", "expense_date"], name="expense_branch_date_idx"),
        ),
    ]
