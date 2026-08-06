from django.db import transaction
from django.utils import timezone

from accounts.models import User
from common.display import localized_system_text
from organizations.models import BranchMembership

from .models import Notification, NotificationRecipient, OutboxEvent


MEMBERSHIP_ROLE_MAP = {
    "housekeeping": BranchMembership.MembershipRole.HOUSEKEEPER,
    "housekeeping_lead": BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
    "manager": BranchMembership.MembershipRole.MANAGER,
    "qc": BranchMembership.MembershipRole.QC,
    "warehouse": BranchMembership.MembershipRole.WAREHOUSE,
    "technician": BranchMembership.MembershipRole.TECHNICIAN,
}


def users_for_branch_roles(branch_id, roles):
    membership_roles = [MEMBERSHIP_ROLE_MAP[role] for role in roles if role in MEMBERSHIP_ROLE_MAP]
    global_roles = [role for role in roles if role in User.Role.values]
    users = User.objects.filter(is_active=True, is_deleted=False)
    ids = set()
    if membership_roles:
        ids.update(
            users.filter(
                branch_memberships__branch_id=branch_id,
                branch_memberships__is_active=True,
                branch_memberships__membership_role__in=membership_roles,
            ).values_list("id", flat=True)
        )
    if global_roles:
        ids.update(
            users.filter(
                role__in=global_roles,
                branch_memberships__branch_id=branch_id,
                branch_memberships__is_active=True,
            ).values_list("id", flat=True)
        )
    return users.filter(id__in=ids)


@transaction.atomic
def notify_task(
    task,
    notification_type,
    title,
    body,
    *,
    deduplication_key,
    users=None,
    roles=None,
    payload=None,
):
    recipient_ids = set()
    if users:
        recipient_ids.update(user.id for user in users if user and user.is_active and not user.is_deleted)
    if roles:
        recipient_ids.update(users_for_branch_roles(task.branch_id, roles).values_list("id", flat=True))
    if not recipient_ids:
        return None
    outbox, created = OutboxEvent.objects.get_or_create(
        deduplication_key=str(deduplication_key)[:120],
        defaults={
            "event_type": notification_type,
            "aggregate_type": "HOUSEKEEPING_TASK",
            "aggregate_id": str(task.id),
            "payload": payload or {},
        },
    )
    if not created:
        return Notification.objects.filter(
            task=task,
            notification_type=notification_type,
            payload__deduplicationKey=str(deduplication_key)[:120],
        ).first()
    notification_payload = {**(payload or {}), "deduplicationKey": str(deduplication_key)[:120]}
    notification = Notification.objects.create(
        branch=task.branch,
        task=task,
        notification_type=notification_type,
        title=localized_system_text(title),
        body=localized_system_text(body),
        object_type="HOUSEKEEPING_TASK",
        object_id=str(task.id),
        payload=notification_payload,
    )
    NotificationRecipient.objects.bulk_create(
        [
            NotificationRecipient(notification=notification, user_id=user_id)
            for user_id in recipient_ids
        ],
        ignore_conflicts=True,
    )
    outbox.payload = {
        **outbox.payload,
        "notificationId": str(notification.id),
        "recipientIds": [str(user_id) for user_id in recipient_ids],
    }
    outbox.save(update_fields=["payload"])
    return notification


@transaction.atomic
def mark_notification_read(user, recipient_id):
    try:
        recipient = NotificationRecipient.objects.select_for_update().select_related("notification").get(
            pk=recipient_id,
            user=user,
        )
    except NotificationRecipient.DoesNotExist:
        return None
    if recipient.read_at is None:
        recipient.read_at = timezone.now()
        recipient.save(update_fields=["read_at"])
    return recipient
