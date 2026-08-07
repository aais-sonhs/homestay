from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


def backfill_branch_owners(apps, schema_editor):
    Branch = apps.get_model("housekeeping", "Branch")
    BranchMembership = apps.get_model("housekeeping", "BranchMembership")
    BranchOwnershipHistory = apps.get_model("housekeeping", "BranchOwnershipHistory")
    User = apps.get_model("accounts", "User")

    platform_admin = (
        User.objects.filter(is_active=True, is_superuser=True, is_deleted=False)
        .order_by("id")
        .first()
    )
    unresolved = []
    for branch in Branch.objects.all().iterator():
        owner_id = branch.owner_id
        if owner_id is None:
            manager_ids = list(
                BranchMembership.objects.filter(
                    branch_id=branch.id,
                    is_active=True,
                    membership_role="MANAGER",
                    user__is_active=True,
                    user__is_deleted=False,
                )
                .order_by("user_id")
                .values_list("user_id", flat=True)
                .distinct()
            )
            if len(manager_ids) != 1:
                unresolved.append(f"{branch.code} ({len(manager_ids)} quản lý đang hoạt động)")
                continue
            owner_id = manager_ids[0]
            branch.owner_id = owner_id
            branch.save(update_fields=["owner"])

        BranchMembership.objects.update_or_create(
            branch_id=branch.id,
            user_id=owner_id,
            defaults={
                "is_active": True,
                "membership_role": "MANAGER",
                "can_manage_team": True,
            },
        )
        BranchOwnershipHistory.objects.get_or_create(
            branch_id=branch.id,
            source="LEGACY_BACKFILL",
            defaults={
                "new_owner_id": owner_id,
                "changed_by_id": platform_admin.id if platform_admin else None,
            },
        )

    if unresolved:
        details = ", ".join(unresolved)
        raise RuntimeError(
            "Không thể tự gán chủ chi nhánh. Mỗi chi nhánh cũ phải có đúng một "
            f"membership MANAGER đang hoạt động trước khi migrate: {details}"
        )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounts", "0009_ensure_platform_admin"),
        ("housekeeping", "0010_branch_owner"),
    ]

    operations = [
        migrations.CreateModel(
            name="BranchOwnershipHistory",
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
                    "source",
                    models.CharField(
                        choices=[
                            ("CREATED", "Tạo chi nhánh"),
                            ("TRANSFERRED", "Chuyển chủ"),
                            ("LEGACY_BACKFILL", "Chuẩn hóa dữ liệu cũ"),
                        ],
                        max_length=24,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ownership_history",
                        to="housekeeping.branch",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="branch_ownership_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "new_owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="new_branch_ownership_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "previous_owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="previous_branch_ownership_records",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "branch_ownership_history",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.RunPython(backfill_branch_owners, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="branch",
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="owned_branches",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
