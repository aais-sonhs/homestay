from django.db import migrations


def translate_legacy_checkin_text(apps, schema_editor):
    HousekeepingTask = apps.get_model("housekeeping", "HousekeepingTask")
    HousekeepingTask.objects.filter(
        special_request="Ưu tiên phòng có khách sắp check-in."
    ).update(special_request="Ưu tiên phòng có khách sắp nhận phòng.")


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0008_translate_seeded_display_text"),
    ]

    operations = [
        migrations.RunPython(
            translate_legacy_checkin_text,
            migrations.RunPython.noop,
        ),
    ]
