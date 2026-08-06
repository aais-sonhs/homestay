from django.contrib import admin

from .models import (
    Area,
    Booking,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    ChecklistItemDefinition,
    ChecklistTemplate,
    ChecklistVersion,
    HousekeepingActivityLog,
    HousekeepingTeam,
    HousekeepingTask,
    IssueTicket,
    Notification,
    NotificationRecipient,
    OfflineMutationReceipt,
    OutboxEvent,
    QCFailedItem,
    QCTask,
    ReworkRound,
    Room,
    Shift,
    ShiftAssignment,
    Skill,
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


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "branch", "floor", "area", "status")
    list_filter = ("branch", "status", "floor")
    search_fields = ("code", "name")


admin.site.register(Branch)
admin.site.register(BranchHousekeepingPolicy)
admin.site.register(Area)
admin.site.register(Skill)
admin.site.register(HousekeepingTeam)
admin.site.register(BranchMembership)
admin.site.register(Shift)
admin.site.register(ShiftAssignment)
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
