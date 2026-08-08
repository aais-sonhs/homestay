from django.urls import path

from . import api, views


app_name = "organizations"

urlpatterns = [
    path("api/v1/organizations/staff", api.staff_collection, name="api-staff-collection"),
    path("api/v1/organizations/staff/", api.staff_collection),
    path(
        "api/v1/organizations/staff/assign-existing",
        api.staff_assign_existing,
        name="api-staff-assign-existing",
    ),
    path(
        "api/v1/organizations/staff/assign-existing/",
        api.staff_assign_existing,
    ),
    path("settings/branches/", views.branch_list, name="branch-list"),
    path("settings/branches/create/", views.branch_create, name="branch-create"),
    path("settings/branches/<uuid:branch_id>/edit/", views.branch_update, name="branch-update"),
    path("settings/branches/<uuid:branch_id>/status/", views.branch_toggle_active, name="branch-toggle-active"),
    path("branch-owners/", views.branch_owner_list, name="branch-owner-list"),
    path("branch-owners/create/", views.branch_owner_create, name="branch-owner-create"),
    path("branch-owners/<int:owner_id>/edit/", views.branch_owner_update, name="branch-owner-update"),
    path("staff/", views.branch_staff_list, name="branch-staff-list"),
    path("staff/create/", views.branch_staff_create, name="branch-staff-create"),
    path(
        "staff/<int:membership_id>/edit/",
        views.branch_staff_update,
        name="branch-staff-update",
    ),
    path(
        "staff/<int:membership_id>/delete/",
        views.branch_staff_delete,
        name="branch-staff-delete",
    ),
    path(
        "staff/<int:membership_id>/toggle-active/",
        views.branch_staff_toggle_active,
        name="branch-staff-toggle-active",
    ),
]
