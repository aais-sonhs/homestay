from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User

from .models import (
    Booking,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    HousekeepingTask,
    HousekeepingTeam,
    OfflineMutationReceipt,
    QCFailedItem,
    QCTask,
    ReworkRound,
    Room,
    TaskChecklistItem,
    TaskSLAState,
)


class DomainFoundationModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="domain-housekeeper",
            password="Test@2026",
            role=User.Role.HOUSEKEEPING,
        )
        self.branch = Branch.objects.create(
            code="DOMAIN", name="Domain Branch", owner=self.user
        )
        self.room = Room.objects.create(
            branch=self.branch,
            code="D101",
            name="Phòng D101",
            status=Room.Status.WAITING_CLEANING,
        )
        self.booking = Booking.objects.create(
            branch=self.branch,
            room=self.room,
            code="BOOK-D101",
        )
        self.template = ChecklistTemplate.objects.create(
            branch=self.branch,
            code="CHECKOUT",
            name="Checkout cleaning",
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
        )
        self.version = ChecklistVersion.objects.create(
            template=self.template,
            version_number=1,
            version_label="v1",
            status=ChecklistVersion.Status.PUBLISHED,
            published_at=timezone.now(),
        )
        self.definition = ChecklistItemDefinition.objects.create(
            version=self.version,
            key="bed",
            group_name="Phòng ngủ",
            title="Thay ga giường",
            item_type=TaskChecklistItem.ItemType.CHECKBOX,
            is_required=True,
            sort_order=1,
        )
        self.task = HousekeepingTask.objects.create(
            code="DOMAIN-TASK-001",
            branch=self.branch,
            room=self.room,
            booking=self.booking,
            booking_code=self.booking.code,
            task_type=HousekeepingTask.TaskType.CHECKOUT_CLEANING,
            priority=HousekeepingTask.Priority.NORMAL,
            status=HousekeepingTask.Status.IN_PROGRESS,
            assignee=self.user,
            checklist_template_version=self.version,
            scheduled_start_at=timezone.now(),
            due_at=timezone.now() + timedelta(minutes=45),
        )

    def test_task_checklist_snapshot_does_not_change_with_definition(self):
        snapshot = TaskChecklistItem.objects.create(
            task=self.task,
            definition=self.definition,
            definition_key=self.definition.key,
            group_name=self.definition.group_name,
            title=self.definition.title,
            item_type=self.definition.item_type,
            is_required=self.definition.is_required,
        )
        self.definition.title = "Nội dung template đã đổi"
        self.definition.save(update_fields=["title"])
        snapshot.refresh_from_db()
        self.assertEqual(snapshot.title, "Thay ga giường")
        self.assertEqual(snapshot.definition.title, "Nội dung template đã đổi")

    def test_offline_idempotency_key_is_unique_per_user(self):
        OfflineMutationReceipt.objects.create(
            user=self.user,
            task=self.task,
            idempotency_key="client-mutation-001",
            operation="CHECKLIST_UPDATE",
            payload_hash="a" * 64,
            base_version=1,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            OfflineMutationReceipt.objects.create(
                user=self.user,
                task=self.task,
                idempotency_key="client-mutation-001",
                operation="CHECKLIST_UPDATE",
                payload_hash="b" * 64,
                base_version=1,
            )

    def test_qc_and_rework_rounds_keep_explicit_links(self):
        item = TaskChecklistItem.objects.create(
            task=self.task,
            definition=self.definition,
            definition_key=self.definition.key,
            title=self.definition.title,
        )
        qc_round = QCTask.objects.create(
            task=self.task,
            round_number=1,
            status=QCTask.Status.REJECTED,
            reason="Ga giường còn nhăn",
            checklist_snapshot=[{"itemId": str(item.id), "title": item.title}],
        )
        failed = QCFailedItem.objects.create(
            qc_round=qc_round,
            checklist_item=item,
            reason="Ga giường còn nhăn",
        )
        rework = ReworkRound.objects.create(
            task=self.task,
            source_qc_round=qc_round,
            round_number=1,
            status=ReworkRound.Status.PENDING,
            checklist_snapshot=qc_round.checklist_snapshot,
        )
        failed.resolved_in_rework = rework
        failed.save(update_fields=["resolved_in_rework"])

        qc_round.reason = "Nội dung QC được lưu riêng"
        qc_round.save(update_fields=["reason"])
        rework.refresh_from_db()
        self.assertEqual(rework.source_qc_round_id, qc_round.id)
        self.assertEqual(rework.checklist_snapshot[0]["title"], "Thay ga giường")
        self.assertEqual(failed.resolved_in_rework_id, rework.id)


class HousekeepingSeedDomainTests(TestCase):
    def test_seed_creates_domain_foundation_for_demo_tasks(self):
        output = StringIO()
        call_command("seed_demo_data", stdout=output)
        call_command("seed_housekeeping_data", stdout=output)

        self.assertEqual(BranchHousekeepingPolicy.objects.count(), 2)
        self.assertEqual(HousekeepingTeam.objects.count(), 2)
        self.assertEqual(User.objects.count(), 10)
        self.assertEqual(
            User.objects.filter(username="housekeeping_lead", role=User.Role.HOUSEKEEPING).count(),
            1,
        )
        self.assertEqual(
            BranchMembership.objects.filter(
                user__username="housekeeping_lead",
                membership_role=BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
                is_active=True,
            ).count(),
            2,
        )
        self.assertEqual(
            BranchMembership.objects.filter(
                user__username__in={"customer_service", "viewer"},
                membership_role=BranchMembership.MembershipRole.VIEWER,
                is_active=True,
            ).count(),
            4,
        )
        self.assertEqual(
            BranchMembership.objects.filter(
                user__username="sales",
                membership_role=BranchMembership.MembershipRole.SALES,
                is_active=True,
            ).count(),
            2,
        )
        self.assertTrue(HousekeepingTask.objects.exclude(booking=None).exists())
        self.assertFalse(HousekeepingTask.objects.filter(checklist_template_version=None).exists())
        self.assertEqual(TaskSLAState.objects.count(), HousekeepingTask.objects.count())
