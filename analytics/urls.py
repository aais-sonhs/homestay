from django.urls import path

from . import views


app_name = "analytics"

urlpatterns = [
    path("overview/", views.owner_dashboard, name="owner-dashboard"),
]
