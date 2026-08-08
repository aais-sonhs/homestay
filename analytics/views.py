from datetime import date

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render
from django.utils import timezone

from reservations.selectors import revenue_branch_queryset

from .selectors import build_owner_dashboard, can_view_owner_dashboard


def _selected_date(request):
    raw_value = str(request.GET.get("date") or "").strip()
    try:
        return date.fromisoformat(raw_value) if raw_value else timezone.localdate()
    except ValueError:
        return timezone.localdate()


def _selected_branch_id(request, branches):
    branch_id = str(request.GET.get("branchId") or "").strip()
    if not branch_id:
        return ""
    try:
        return branch_id if branches.filter(pk=branch_id).exists() else ""
    except (ValidationError, ValueError):
        return ""


@login_required
def owner_dashboard(request):
    if not can_view_owner_dashboard(request.user):
        raise PermissionDenied("Bạn không có quyền xem dashboard dành cho chủ homestay.")
    branches = revenue_branch_queryset(request.user)
    selected_date = _selected_date(request)
    selected_branch_id = _selected_branch_id(request, branches)
    dashboard = build_owner_dashboard(
        request.user,
        selected_date,
        branch_id=selected_branch_id or None,
    )
    return render(
        request,
        "analytics/owner_dashboard.html",
        {
            "branches": branches,
            "selected_date": selected_date,
            "selected_branch_id": selected_branch_id,
            "dashboard": dashboard,
        },
    )
