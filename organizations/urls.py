from django.urls import path

from . import views


app_name = "organizations"

urlpatterns = [
    path("settings/branches/", views.branch_list, name="branch-list"),
    path("settings/branches/create/", views.branch_create, name="branch-create"),
    path("settings/branches/<uuid:branch_id>/edit/", views.branch_update, name="branch-update"),
    path("settings/branches/<uuid:branch_id>/status/", views.branch_toggle_active, name="branch-toggle-active"),
    path("branch-owners/", views.branch_owner_list, name="branch-owner-list"),
    path("branch-owners/create/", views.branch_owner_create, name="branch-owner-create"),
    path("branch-owners/<int:owner_id>/edit/", views.branch_owner_update, name="branch-owner-update"),
]
