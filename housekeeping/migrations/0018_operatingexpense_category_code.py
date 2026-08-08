from django.db import migrations, models


def classify_expense_categories(apps, schema_editor):
    OperatingExpense = apps.get_model("housekeeping", "OperatingExpense")
    category_terms = {
        "HOUSEKEEPING": ("housekeeping", "buồng", "vệ sinh", "giặt", "dọn"),
        "TECHNICAL_MAINTENANCE": ("kỹ thuật", "bảo trì", "sửa", "maintenance", "repair"),
        "UTILITIES": ("điện", "nước", "internet", "tiện ích"),
        "SUPPLIES": ("vật tư", "tiêu hao", "amenity"),
        "PAYROLL": ("nhân sự", "tiền công", "lương"),
        "CHANNEL_FEES": ("kênh bán", "ota", "hoa hồng"),
    }
    for expense in OperatingExpense.objects.all().only("id", "category", "name"):
        haystack = f"{expense.category} {expense.name}".lower()
        code = "OTHER"
        for candidate, terms in category_terms.items():
            if any(term in haystack for term in terms):
                code = candidate
                break
        OperatingExpense.objects.filter(pk=expense.pk).update(category_code=code)


class Migration(migrations.Migration):
    dependencies = [("housekeeping", "0017_capital_and_operating_expenses")]

    operations = [
        migrations.AddField(
            model_name="operatingexpense",
            name="category_code",
            field=models.CharField(
                choices=[
                    ("HOUSEKEEPING", "Housekeeping / vệ sinh"),
                    ("TECHNICAL_MAINTENANCE", "Kỹ thuật / bảo trì"),
                    ("UTILITIES", "Điện, nước và tiện ích"),
                    ("SUPPLIES", "Vật tư tiêu hao"),
                    ("PAYROLL", "Nhân sự / tiền công"),
                    ("CHANNEL_FEES", "Phí kênh bán"),
                    ("OTHER", "Chi phí khác"),
                ],
                db_index=True,
                default="OTHER",
                max_length=24,
            ),
        ),
        migrations.RunPython(classify_expense_categories, migrations.RunPython.noop),
    ]
