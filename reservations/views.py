from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from common.access import can_view_booking_guest
from common.list_views import paginate_context
from housekeeping.models import Booking
from housekeeping.services import request_context
from organizations.selectors import branch_queryset_for_user

from .forms import (
    BookingCancelForm,
    BookingCreateForm,
    BookingSpecialRequestFormSet,
    BookingUpdateForm,
    special_request_formset_initial,
)
from .selectors import (
    booking_queryset_for_user,
    can_create_any_booking,
    can_create_booking_for_branch,
)
from .services import (
    BookingCreationError,
    BookingOperationError,
    cancel_booking,
    create_booking,
    update_booking,
)


def _special_request_formset(request, *, initial=None):
    if request.method != "POST":
        return BookingSpecialRequestFormSet(initial=initial, prefix="requests")
    data = request.POST
    if "requests-TOTAL_FORMS" not in data:
        data = request.POST.copy()
        legacy_text = str(request.POST.get("special_requests") or "").strip()
        data.update(
            {
                "requests-TOTAL_FORMS": "1" if legacy_text else "0",
                "requests-INITIAL_FORMS": "0",
                "requests-MIN_NUM_FORMS": "0",
                "requests-MAX_NUM_FORMS": "20",
            }
        )
        if legacy_text:
            data.update(
                {
                    "requests-0-request_type": "OTHER",
                    "requests-0-applies_to": "ALL",
                    "requests-0-priority": "NORMAL",
                    "requests-0-description": legacy_text,
                    "requests-0-quantity": "",
                }
            )
    return BookingSpecialRequestFormSet(data=data, prefix="requests")


@login_required
def booking_list(request):
    queryset = booking_queryset_for_user(request.user)
    branches = branch_queryset_for_user(request.user)
    query = str(request.GET.get("q") or "").strip()
    status = str(request.GET.get("status") or "").strip()
    branch_id = str(request.GET.get("branchId") or "").strip()
    selected_date = str(request.GET.get("date") or "").strip()
    if query:
        guest_branch_ids = [
            branch.id
            for branch in branches
            if can_view_booking_guest(request.user, branch)
        ]
        guest_query = Q(branch_id__in=guest_branch_ids) & (
            Q(guest_name__icontains=query) | Q(guest_phone__icontains=query)
        )
        queryset = queryset.filter(
            Q(code__icontains=query) | Q(room__code__icontains=query) | guest_query
        )
    if status in Booking.Status.values:
        queryset = queryset.filter(status=status)
    if branch_id:
        try:
            branch_allowed = branches.filter(pk=branch_id).exists()
        except (ValidationError, ValueError):
            branch_allowed = False
        queryset = queryset.filter(branch_id=branch_id) if branch_allowed else queryset.none()
    if selected_date:
        try:
            day = date.fromisoformat(selected_date)
        except ValueError:
            messages.error(request, "Ngày lọc booking không hợp lệ.")
        else:
            queryset = queryset.filter(Q(checkin_at__date=day) | Q(checkout_at__date=day))
    queryset = queryset.order_by("-checkin_at", "branch__name", "room__code")
    page_context = paginate_context(request, queryset, context_object_name="bookings", per_page=20)
    booking_rows = [
        {
            "booking": booking,
            "canViewGuest": can_view_booking_guest(request.user, booking.branch),
            "canManage": (
                booking.status == Booking.Status.BOOKED
                and can_create_booking_for_branch(request.user, booking.branch)
            ),
        }
        for booking in page_context["bookings"]
    ]
    page_context["booking_rows"] = booking_rows
    return render(
        request,
        "reservations/booking_list.html",
        {
            **page_context,
            "branches": branches,
            "statuses": Booking.Status.choices,
            "filters": {
                "q": query,
                "status": status,
                "branchId": branch_id,
                "date": selected_date,
            },
            "can_create_booking": can_create_any_booking(request.user),
        },
    )


@login_required
def booking_create(request):
    if not can_create_any_booking(request.user):
        messages.error(request, "Bạn chưa được cấp quyền tạo booking tại chi nhánh nào.")
        return redirect("reservations:booking-list")
    form = BookingCreateForm(request.POST or None, user=request.user)
    special_request_formset = _special_request_formset(request)
    if request.method == "POST":
        form_is_valid = form.is_valid()
        requests_are_valid = special_request_formset.is_valid()
    else:
        form_is_valid = requests_are_valid = False
    if request.method == "POST" and form_is_valid and requests_are_valid:
        cleaned_data = dict(form.cleaned_data)
        cleaned_data["special_request_items"] = special_request_formset.cleaned_data
        try:
            booking, tasks = create_booking(
                request.user,
                cleaned_data,
                request_context(request),
            )
        except BookingCreationError as error:
            form.add_error(None, str(error))
        else:
            messages.success(
                request,
                f"Đã tạo booking {booking.code} và lên lịch tự động: "
                f"{tasks[0].code}, {tasks[1].code}.",
            )
            query = urlencode(
                {
                    "date": timezone.localdate(booking.checkin_at).isoformat(),
                    "branchId": str(booking.branch_id),
                }
            )
            return redirect(f"{reverse('room_operations:schedule')}?{query}")
    return render(
        request,
        "reservations/booking_form.html",
        {
            "form": form,
            "special_request_formset": special_request_formset,
            "page_title": "Tạo booking cho khách",
            "page_description": "Nhân viên Kinh doanh nhập booking hộ khách tại chi nhánh được phân quyền.",
            "submit_label": "Tạo booking và lên lịch dọn",
        },
    )


@login_required
def booking_update(request, booking_id):
    booking = get_object_or_404(booking_queryset_for_user(request.user), pk=booking_id)
    if not can_create_booking_for_branch(request.user, booking.branch):
        raise PermissionDenied("Bạn không có quyền cập nhật booking này.")
    if booking.status != Booking.Status.BOOKED:
        messages.error(request, "Chỉ booking đang ở trạng thái Đã đặt mới được chỉnh sửa.")
        return redirect("reservations:booking-list")

    form = BookingUpdateForm(request.POST or None, user=request.user, instance=booking)
    special_request_formset = _special_request_formset(
        request,
        initial=special_request_formset_initial(booking),
    )
    if request.method == "POST":
        form_is_valid = form.is_valid()
        requests_are_valid = special_request_formset.is_valid()
    else:
        form_is_valid = requests_are_valid = False
    if request.method == "POST" and form_is_valid and requests_are_valid:
        cleaned_data = dict(form.cleaned_data)
        cleaned_data["special_request_items"] = special_request_formset.cleaned_data
        try:
            booking, tasks = update_booking(
                request.user,
                booking.id,
                cleaned_data,
                form.cleaned_data["version"],
                request_context(request),
            )
        except BookingOperationError as error:
            form.add_error(None, str(error))
            booking.refresh_from_db()
        else:
            messages.success(
                request,
                f"Đã cập nhật booking {booking.code} và đồng bộ {len(tasks)} công việc liên quan.",
            )
            return redirect("reservations:booking-list")
    return render(
        request,
        "reservations/booking_form.html",
        {
            "form": form,
            "special_request_formset": special_request_formset,
            "booking": booking,
            "page_title": f"Chỉnh sửa booking {booking.code}",
            "page_description": (
                f"Chi nhánh {booking.branch.name}. Đổi giờ, phòng hoặc yêu cầu khách "
                "sẽ đồng bộ sang lịch dọn chưa bắt đầu."
            ),
            "submit_label": "Lưu và đồng bộ lịch dọn",
            "cancel_form": BookingCancelForm(initial={"version": booking.version}),
            "change_logs": booking.change_logs.select_related("changed_by")[:20],
        },
    )


@login_required
def booking_cancel(request, booking_id):
    if request.method != "POST":
        raise PermissionDenied("Thao tác hủy booking yêu cầu phương thức POST.")
    booking = get_object_or_404(booking_queryset_for_user(request.user), pk=booking_id)
    if not can_create_booking_for_branch(request.user, booking.branch):
        raise PermissionDenied("Bạn không có quyền hủy booking này.")
    form = BookingCancelForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vui lòng nhập lý do hủy booking hợp lệ.")
        return redirect("reservations:booking-update", booking_id=booking.id)
    try:
        booking, tasks = cancel_booking(
            request.user,
            booking.id,
            form.cleaned_data["version"],
            form.cleaned_data["reason"],
            request_context(request),
        )
    except BookingOperationError as error:
        messages.error(request, str(error))
        return redirect("reservations:booking-update", booking_id=booking.id)
    messages.success(
        request,
        f"Đã hủy booking {booking.code} và hủy {len(tasks)} công việc liên quan.",
    )
    return redirect("reservations:booking-list")
