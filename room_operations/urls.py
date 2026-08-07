from django.urls import path

from . import views


app_name = "room_operations"

urlpatterns = [
    path("operations/schedule/", views.operations_schedule, name="schedule"),
    path("operations/rooms/", views.room_readiness_board, name="room-readiness"),
    path("operations/rooms/<uuid:room_id>/", views.room_profile, name="room-profile"),
    path("operations/stop-sell/", views.stop_sell_list, name="stop-sell-list"),
    path("operations/stop-sell/create/", views.stop_sell_create, name="stop-sell-create"),
    path(
        "operations/stop-sell/<uuid:stop_sell_id>/request-reopen/",
        views.stop_sell_request_reopen,
        name="stop-sell-request-reopen",
    ),
    path(
        "operations/stop-sell/<uuid:stop_sell_id>/confirm-reopen/",
        views.stop_sell_confirm_reopen,
        name="stop-sell-confirm-reopen",
    ),
    path(
        "operations/stop-sell/<uuid:stop_sell_id>/cancel/",
        views.stop_sell_cancel,
        name="stop-sell-cancel",
    ),
    path(
        "operations/blockers/<uuid:blocker_id>/confirm-clearance/",
        views.blocker_confirm_clearance,
        name="blocker-confirm-clearance",
    ),
]
