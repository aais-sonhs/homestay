from django.contrib import admin

from .models import (
    Booking,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    GuestServiceRequest,
    GuestServiceRequestEvent,
    HousekeepingActivityLog,
    HousekeepingTask,
    IssueTicket,
    Notification,
    NotificationRecipient,
    OfflineMutationReceipt,
    OutboxEvent,
    QCFailedItem,
    QCTask,
    ReworkRound,
    SLAEscalationEvent,
    SLAPolicy,
    SupplyRequest,
    SupplyLocation,
    TaskChecklistItem,
    TaskAssignment,
    TaskHandover,
    TaskPause,
    TaskPhoto,
    TaskRoomVerification,
    TaskSLAState,
    TaskStatusHistory,
)


@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(admin.ModelAdmin):
    list_display = ("code", "room", "branch", "task_type", "priority", "status", "assignee", "due_at", "progress_percent")
    list_filter = ("branch", "task_type", "priority", "status")
    search_fields = ("code", "room__code", "room__name", "booking_code", "assignee__username")
    readonly_fields = ("accepted_at", "started_at", "completed_at", "version", "created_at", "updated_at")
    filter_horizontal = ("required_skills",)


@admin.register(GuestServiceRequest)
class GuestServiceRequestAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "room",
        "branch",
        "request_type",
        "priority",
        "status",
        "assignee",
        "due_at",
    )
    list_filter = ("branch", "request_type", "priority", "status", "source")
    search_fields = (
        "code",
        "room__code",
        "booking__code",
        "booking__guest_name",
        "description",
    )
    readonly_fields = (
        "accepted_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "version",
        "created_at",
        "updated_at",
    )


admin.site.register(Booking)
admin.site.register(ChecklistTemplate)
admin.site.register(ChecklistVersion)
admin.site.register(ChecklistItemDefinition)
admin.site.register(TaskChecklistItem)
admin.site.register(TaskAssignment)
admin.site.register(TaskHandover)
admin.site.register(TaskRoomVerification)
admin.site.register(TaskPhoto)
admin.site.register(TaskPause)
admin.site.register(SupplyLocation)
admin.site.register(SupplyRequest)
admin.site.register(IssueTicket)
admin.site.register(QCTask)
admin.site.register(QCFailedItem)
admin.site.register(ReworkRound)
admin.site.register(SLAPolicy)
admin.site.register(TaskSLAState)
admin.site.register(SLAEscalationEvent)
admin.site.register(Notification)
admin.site.register(NotificationRecipient)
admin.site.register(OutboxEvent)
admin.site.register(OfflineMutationReceipt)
admin.site.register(TaskStatusHistory)
admin.site.register(HousekeepingActivityLog)
admin.site.register(GuestServiceRequestEvent)
