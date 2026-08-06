from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import AccessToken, ActivityLog, PasswordHistory, PasswordResetRequest, RefreshToken, User


admin.site.site_header = "Quản trị hệ thống Bliss Home"
admin.site.site_title = "Quản trị Bliss Home"
admin.site.index_title = "Quản trị hệ thống"


@admin.register(User)
class BlissHomeUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            "Bliss Home",
            {
                "fields": (
                    "role",
                    "phone_number",
                    "avatar",
                    "is_deleted",
                    "is_permanently_disabled",
                    "disabled_by_admin",
                    "locked_due_to_failed_logins",
                    "password_changed_at",
                )
            },
        ),
    )


@admin.register(PasswordResetRequest)
class PasswordResetRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "channel", "destination", "status", "created_at")
    list_filter = ("status", "channel")
    readonly_fields = (
        "otp_hash",
        "reset_token_hash",
        "created_at",
        "updated_at",
    )


admin.site.register(AccessToken)
admin.site.register(RefreshToken)
admin.site.register(PasswordHistory)
admin.site.register(ActivityLog)
