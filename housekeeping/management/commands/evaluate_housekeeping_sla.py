import uuid

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from housekeeping.models import HousekeepingTask
from housekeeping.sla import evaluate_task_sla


class Command(BaseCommand):
    help = "Đánh giá thời hạn công việc buồng phòng và tạo cảnh báo, thông báo không trùng lặp."

    def add_arguments(self, parser):
        parser.add_argument("--branch", help="Branch UUID or code")
        parser.add_argument("--task-id", help="Đánh giá một công việc theo mã UUID")
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--at", help="ISO-8601 evaluation time (mainly for controlled jobs/tests)")

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit < 1:
            raise CommandError("--limit must be greater than zero")
        at = timezone.now()
        if options.get("at"):
            at = parse_datetime(options["at"])
            if at is None:
                raise CommandError("--at must be a valid ISO-8601 datetime")
            if timezone.is_naive(at):
                at = timezone.make_aware(at)

        queryset = HousekeepingTask.objects.select_related("branch", "room", "assignee").exclude(
            status=HousekeepingTask.Status.CANCELLED
        )
        if options.get("task_id"):
            queryset = queryset.filter(pk=options["task_id"])
        if options.get("branch"):
            branch = options["branch"]
            try:
                branch_id = uuid.UUID(str(branch))
            except ValueError:
                queryset = queryset.filter(branch__code=branch)
            else:
                queryset = queryset.filter(branch_id=branch_id)

        evaluated = 0
        for task in queryset.order_by("created_at", "id")[:limit]:
            evaluate_task_sla(task, at=at)
            evaluated += 1
        self.stdout.write(self.style.SUCCESS(f"Đã đánh giá thời hạn cho {evaluated} công việc buồng phòng."))
