from django.contrib import admin

from .models import RoomAsset, RoomBlocker, RoomBlockerHistory, RoomStopSell, RoomStopSellHistory


@admin.register(RoomAsset)
class RoomAssetAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "branch",
        "room",
        "category",
        "status",
        "next_maintenance_at",
        "is_active",
    )
    list_filter = ("branch", "category", "status", "is_active")
    search_fields = ("code", "name", "serial_number", "room__code")


admin.site.register(RoomBlocker)
admin.site.register(RoomBlockerHistory)
admin.site.register(RoomStopSell)
admin.site.register(RoomStopSellHistory)
