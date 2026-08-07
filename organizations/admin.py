from django.contrib import admin

from .models import (
    Area,
    Branch,
    BranchHousekeepingPolicy,
    BranchMembership,
    BranchOwnershipHistory,
    HousekeepingTeam,
    Room,
    Shift,
    ShiftAssignment,
    Skill,
)


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
admin.site.register(BranchOwnershipHistory)
admin.site.register(Shift)
admin.site.register(ShiftAssignment)
