from django.db import migrations


def ensure_platform_admin(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(username="admin", is_deleted=False).update(
        role="founder",
        is_active=True,
        is_staff=True,
        is_superuser=True,
        is_permanently_disabled=False,
        disabled_by_admin=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_add_branch_owner_role"),
    ]

    operations = [
        migrations.RunPython(ensure_platform_admin, migrations.RunPython.noop),
    ]
