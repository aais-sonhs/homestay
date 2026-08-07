from django.urls import include, path

from . import views


app_name = "housekeeping"

urlpatterns = [
    path("guest-requests/", views.guest_request_list, name="guest-request-list"),
    path("guest-requests/create/", views.guest_request_create, name="guest-request-create"),
    path("guest-requests/<uuid:request_id>/", views.guest_request_detail, name="guest-request-detail"),
    path(
        "guest-requests/<uuid:request_id>/<str:action>/",
        views.guest_request_web_action,
        name="guest-request-action",
    ),
    path("housekeeping/tasks/", views.task_list, name="task-list"),
    path("housekeeping/tasks/create/", views.task_create, name="task-create"),
    path("housekeeping/operations/", views.operations_dashboard, name="operations-dashboard"),
    path("housekeeping/support/", views.support_queue, name="support-queue"),
    path(
        "housekeeping/support/<str:entity_type>/<uuid:entity_id>/",
        views.support_web_action,
        name="support-web-action",
    ),
    path("housekeeping/activity/", views.activity_log, name="activity-log"),
    path("housekeeping/notifications/", views.notification_center, name="notification-center"),
    path(
        "housekeeping/notifications/<int:recipient_id>/read/",
        views.notification_web_read,
        name="notification-web-read",
    ),
    path("housekeeping/tasks/<uuid:task_id>/", views.task_detail, name="task-detail"),
    path("housekeeping/tasks/<uuid:task_id>/<str:action>/", views.task_web_action, name="task-web-action"),
    path("api/v1/housekeeping/", include("housekeeping.api.urls")),
]
