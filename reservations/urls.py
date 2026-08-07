from django.urls import path

from . import views


app_name = "reservations"

urlpatterns = [
    path("reports/costs/", views.costs_dashboard, name="costs-dashboard"),
    path("reports/profit/", views.profit_dashboard, name="profit-dashboard"),
    path("reports/costs/capital/", views.capital_list, name="capital-list"),
    path("reports/costs/capital/create/", views.capital_create, name="capital-create"),
    path("reports/costs/capital/<uuid:entry_id>/edit/", views.capital_update, name="capital-update"),
    path("reports/costs/operating/", views.expense_list, name="expense-list"),
    path("reports/costs/operating/create/", views.expense_create, name="expense-create"),
    path("reports/costs/operating/<uuid:expense_id>/edit/", views.expense_update, name="expense-update"),
    path("reports/revenue/daily/", views.revenue_daily, name="revenue-daily"),
    path("reports/revenue/monthly/", views.revenue_monthly, name="revenue-monthly"),
    path("bookings/", views.booking_list, name="booking-list"),
    path("bookings/create/", views.booking_create, name="booking-create"),
    path("bookings/<uuid:booking_id>/edit/", views.booking_update, name="booking-update"),
    path(
        "bookings/<uuid:booking_id>/financials/",
        views.booking_financial_update,
        name="booking-financial-update",
    ),
    path("bookings/<uuid:booking_id>/cancel/", views.booking_cancel, name="booking-cancel"),
]
