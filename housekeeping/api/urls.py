from django.urls import path

from . import views


urlpatterns = [
    path("dashboard/sla", views.sla_dashboard, name="api-sla-dashboard"),
    path("dashboard/performance", views.performance_dashboard, name="api-performance-dashboard"),
    path("notifications", views.notification_list, name="api-notification-list"),
    path("notifications/<int:recipient_id>/read", views.notification_read, name="api-notification-read"),
    path("sync/batch", views.sync_batch, name="api-sync-batch"),
    path("sync/conflicts/<uuid:receipt_id>", views.sync_conflict, name="api-sync-conflict"),
    path(
        "sync/conflicts/<uuid:receipt_id>/resolve",
        views.sync_conflict_resolve,
        name="api-sync-conflict-resolve",
    ),
    path(
        "sync/receipts/<uuid:receipt_id>/discard",
        views.sync_receipt_discard,
        name="api-sync-receipt-discard",
    ),
    path("supply-requests", views.supply_queue, name="api-supply-queue"),
    path("supply-requests/<uuid:request_id>", views.supply_queue_update, name="api-supply-queue-update"),
    path("issues", views.issue_queue, name="api-issue-queue"),
    path("issues/<uuid:issue_id>", views.issue_queue_update, name="api-issue-queue-update"),
    path("tasks", views.task_list, name="api-task-list"),
    path("tasks/", views.task_list),
    path("tasks/<uuid:task_id>", views.task_detail, name="api-task-detail"),
    path("tasks/<uuid:task_id>/", views.task_detail),
    path("tasks/<uuid:task_id>/note", views.task_note, name="api-task-note"),
    path("tasks/<uuid:task_id>/completion-summary", views.completion_summary, name="api-completion-summary"),
    path("tasks/<uuid:task_id>/checklist-items/<uuid:item_id>", views.checklist_item, name="api-checklist-item"),
    path(
        "tasks/<uuid:task_id>/checklist-items/<uuid:item_id>/accept-failure",
        views.checklist_failure_accept,
        name="api-checklist-failure-accept",
    ),
    path("tasks/<uuid:task_id>/supply-requests", views.supply_request, name="api-supply-request"),
    path("tasks/<uuid:task_id>/issues", views.issue, name="api-issue"),
    path("tasks/<uuid:task_id>/photos", views.photo, name="api-photo"),
    path("tasks/<uuid:task_id>/media", views.photo, name="api-media"),
    path("tasks/<uuid:task_id>/reassign", views.reassign, name="api-reassign"),
    path("tasks/<uuid:task_id>/handover", views.handover, name="api-handover"),
    path("tasks/<uuid:task_id>/priority", views.priority, name="api-priority"),
    path("tasks/<uuid:task_id>/qc-review", views.qc_review, name="api-qc-review"),
    path(
        "tasks/<uuid:task_id>/qc-rounds/<int:round_number>/review",
        views.qc_review,
        name="api-qc-round-review",
    ),
]

for action in ("accept", "start", "reject", "return", "pause", "resume", "complete", "cancel"):
    urlpatterns.append(
        path(
            f"tasks/<uuid:task_id>/{action}",
            views.task_action,
            {"action": action},
            name=f"api-{action}",
        )
    )

urlpatterns.append(
    path(
        "tasks/<uuid:task_id>/rework/start",
        views.task_action,
        {"action": "rework-start"},
        name="api-rework-start",
    )
)

# Preserve the MVP clients that used trailing slashes while the documented
# contract remains slashless.
urlpatterns += [
    path("dashboard/sla/", views.sla_dashboard),
    path("dashboard/performance/", views.performance_dashboard),
    path("notifications/", views.notification_list),
    path("notifications/<int:recipient_id>/read/", views.notification_read),
    path("sync/batch/", views.sync_batch),
    path("sync/conflicts/<uuid:receipt_id>/", views.sync_conflict),
    path("sync/conflicts/<uuid:receipt_id>/resolve/", views.sync_conflict_resolve),
    path("sync/receipts/<uuid:receipt_id>/discard/", views.sync_receipt_discard),
    path("supply-requests/", views.supply_queue),
    path("supply-requests/<uuid:request_id>/", views.supply_queue_update),
    path("issues/", views.issue_queue),
    path("issues/<uuid:issue_id>/", views.issue_queue_update),
    path("tasks/<uuid:task_id>/completion-summary/", views.completion_summary),
    path("tasks/<uuid:task_id>/note/", views.task_note),
    path("tasks/<uuid:task_id>/checklist-items/<uuid:item_id>/", views.checklist_item),
    path(
        "tasks/<uuid:task_id>/checklist-items/<uuid:item_id>/accept-failure/",
        views.checklist_failure_accept,
    ),
    path("tasks/<uuid:task_id>/supply-requests/", views.supply_request),
    path("tasks/<uuid:task_id>/issues/", views.issue),
    path("tasks/<uuid:task_id>/photos/", views.photo),
    path("tasks/<uuid:task_id>/media/", views.photo),
    path("tasks/<uuid:task_id>/reassign/", views.reassign),
    path("tasks/<uuid:task_id>/handover/", views.handover),
    path("tasks/<uuid:task_id>/priority/", views.priority),
    path("tasks/<uuid:task_id>/qc-review/", views.qc_review),
    path("tasks/<uuid:task_id>/qc-rounds/<int:round_number>/review/", views.qc_review),
    path("tasks/<uuid:task_id>/rework/start/", views.task_action, {"action": "rework-start"}),
]

for action in ("accept", "start", "reject", "return", "pause", "resume", "complete", "cancel"):
    urlpatterns.append(
        path(f"tasks/<uuid:task_id>/{action}/", views.task_action, {"action": action})
    )
