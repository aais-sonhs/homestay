from django.urls import path

from . import views


app_name = "reservations"

urlpatterns = [
    path("bookings/", views.booking_list, name="booking-list"),
    path("bookings/create/", views.booking_create, name="booking-create"),
    path("bookings/<uuid:booking_id>/edit/", views.booking_update, name="booking-update"),
    path("bookings/<uuid:booking_id>/cancel/", views.booking_cancel, name="booking-cancel"),
]
