from django.db import migrations


TASK_TYPE_LABELS = {
    "CHECKOUT_CLEANING": "Dọn phòng sau khi khách trả phòng",
    "STAYOVER_CLEANING": "Dọn phòng đang có khách",
    "CHECKIN_PREPARATION": "Chuẩn bị phòng đón khách",
    "DEEP_CLEANING": "Vệ sinh chuyên sâu",
    "QC_REWORK": "Dọn lại sau kiểm tra chất lượng",
    "PERIODIC_CLEANING": "Vệ sinh định kỳ",
}


def translate_seeded_text(apps, schema_editor):
    HousekeepingTeam = apps.get_model("housekeeping", "HousekeepingTeam")
    Room = apps.get_model("housekeeping", "Room")
    ChecklistTemplate = apps.get_model("housekeeping", "ChecklistTemplate")
    SLAPolicy = apps.get_model("housekeeping", "SLAPolicy")

    HousekeepingTeam.objects.filter(name="Đội Housekeeping").update(
        name="Đội buồng phòng"
    )
    Room.objects.filter(name="Suite S101").update(name="Phòng hạng sang S101")
    Room.objects.filter(room_type__iexact="Deluxe").update(room_type="Cao cấp")
    SLAPolicy.objects.filter(name="SLA Housekeeping mặc định").update(
        name="Thời hạn buồng phòng mặc định"
    )
    for task_type, label in TASK_TYPE_LABELS.items():
        ChecklistTemplate.objects.filter(
            name=f"Checklist {task_type}"
        ).update(name=f"Danh sách kiểm tra {label}")
        ChecklistTemplate.objects.filter(
            name=f"Danh sách kiểm tra {task_type}"
        ).update(name=f"Danh sách kiểm tra {label}")


class Migration(migrations.Migration):
    dependencies = [
        ("housekeeping", "0007_alter_branchmembership_membership_role_and_more"),
    ]

    operations = [
        migrations.RunPython(translate_seeded_text, migrations.RunPython.noop),
    ]
