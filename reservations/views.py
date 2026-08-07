from datetime import date, datetime, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Q,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date

from common.access import can_view_booking_guest
from common.list_views import paginate_context
from housekeeping.models import Booking, CapitalEntry, OperatingExpense
from housekeeping.services import request_context
from organizations.selectors import branch_queryset_for_user

from .forms import (
    BookingCancelForm,
    BookingCreateForm,
    BookingFinancialUpdateForm,
    BookingSpecialRequestFormSet,
    BookingUpdateForm,
    CapitalEntryForm,
    OperatingExpenseForm,
    special_request_formset_initial,
)
from .selectors import (
    booking_queryset_for_user,
    can_view_revenue,
    can_create_any_booking,
    can_create_booking_for_branch,
    revenue_branch_queryset,
)
from .services import (
    BookingCreationError,
    BookingOperationError,
    cancel_booking,
    create_booking,
    update_booking,
    update_booking_financials,
)


MONEY_ZERO = Decimal("0.00")
MONEY_FIELD = DecimalField(max_digits=18, decimal_places=2)


def _booking_total_expression():
    return ExpressionWrapper(
        F("room_charge") + F("service_charge") - F("discount_amount"),
        output_field=MONEY_FIELD,
    )


def _outstanding_expression():
    return ExpressionWrapper(
        _booking_total_expression() - F("paid_amount"),
        output_field=MONEY_FIELD,
    )


def _zero_money_sum(expression):
    return Coalesce(
        Sum(expression),
        Value(MONEY_ZERO),
        output_field=MONEY_FIELD,
    )


def _local_day_start(day):
    return timezone.make_aware(
        datetime.combine(day, time.min),
        timezone.get_current_timezone(),
    )


def _revenue_queryset_for_request(request, branch_id):
    branches = revenue_branch_queryset(request.user)
    queryset = Booking.objects.filter(
        branch__in=branches,
        checkout_at__isnull=False,
    ).exclude(status=Booking.Status.CANCELLED)
    if branch_id:
        try:
            branch_is_allowed = branches.filter(pk=branch_id).exists()
        except (ValidationError, ValueError):
            branch_is_allowed = False
        queryset = queryset.filter(branch_id=branch_id) if branch_is_allowed else queryset.none()
    return queryset, branches


def _revenue_summary(queryset):
    priced_queryset = queryset.annotate(report_total=_booking_total_expression())
    aggregates = priced_queryset.aggregate(
        booking_count=Count("id"),
        priced_booking_count=Count("id", filter=Q(report_total__gt=0)),
        revenue_total=_zero_money_sum(_booking_total_expression()),
        collected_total=_zero_money_sum(F("paid_amount")),
        balance_total=_zero_money_sum(_outstanding_expression()),
    )
    summary = {
        "booking_count": aggregates["booking_count"],
        "priced_booking_count": aggregates["priced_booking_count"],
        "total_amount": aggregates["revenue_total"],
        "paid_amount": aggregates["collected_total"],
        "outstanding_amount": aggregates["balance_total"],
    }
    summary["unpriced_booking_count"] = (
        summary["booking_count"] - summary["priced_booking_count"]
    )
    return summary


def _revenue_rows(queryset, truncation):
    return list(
        queryset.annotate(period=truncation)
        .values("period")
        .annotate(
            booking_count=Count("id"),
            total_amount=_zero_money_sum(_booking_total_expression()),
            collected_total=_zero_money_sum(F("paid_amount")),
            balance_total=_zero_money_sum(_outstanding_expression()),
        )
        .order_by("period")
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
    revenue_branch_ids = (
        set(revenue_branch_queryset(request.user).values_list("id", flat=True))
        if can_view_revenue(request.user)
        else set()
    )
    booking_rows = [
        {
            "booking": booking,
            "canViewGuest": can_view_booking_guest(request.user, booking.branch),
            "canManage": (
                booking.status == Booking.Status.BOOKED
                and can_create_booking_for_branch(request.user, booking.branch)
            ),
            "canEditFinance": (
                booking.status != Booking.Status.CANCELLED
                and booking.branch_id in revenue_branch_ids
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
def booking_financial_update(request, booking_id):
    allowed_branches = revenue_branch_queryset(request.user)
    booking = get_object_or_404(
        Booking.objects.select_related("branch", "room").filter(
            branch__in=allowed_branches,
        ),
        pk=booking_id,
    )
    if booking.status == Booking.Status.CANCELLED:
        messages.error(request, "Không thể cập nhật tài chính của booking đã hủy.")
        return redirect("reservations:booking-list")

    form = BookingFinancialUpdateForm(request.POST or None, instance=booking)
    if request.method == "POST" and form.is_valid():
        try:
            booking = update_booking_financials(
                request.user,
                booking.id,
                form.cleaned_data,
                form.cleaned_data["version"],
                request_context(request),
            )
        except BookingOperationError as error:
            form.add_error(None, str(error))
            booking.refresh_from_db()
        else:
            messages.success(request, f"Đã cập nhật tài chính booking {booking.code}.")
            return redirect("reservations:booking-list")
    return render(
        request,
        "reservations/booking_financial_form.html",
        {
            "form": form,
            "booking": booking,
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


@login_required
def revenue_daily(request):
    if not can_view_revenue(request.user):
        raise PermissionDenied("Bạn không có quyền xem dữ liệu doanh thu.")

    today = timezone.localdate()
    default_from = today.replace(day=1)
    from_date = parse_date(str(request.GET.get("from_date") or "")) or default_from
    to_date = parse_date(str(request.GET.get("to_date") or "")) or today
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    branch_id = str(request.GET.get("branchId") or "").strip()

    queryset, branches = _revenue_queryset_for_request(request, branch_id)
    queryset = queryset.filter(
        checkout_at__gte=_local_day_start(from_date),
        checkout_at__lt=_local_day_start(to_date + timedelta(days=1)),
    )
    rows = _revenue_rows(
        queryset,
        TruncDate("checkout_at", tzinfo=timezone.get_current_timezone()),
    )
    summary = _revenue_summary(queryset)
    summary["period_count"] = len(rows)
    page_context = paginate_context(
        request,
        rows,
        context_object_name="rows",
        per_page=20,
    )
    return render(
        request,
        "reservations/revenue_report.html",
        {
            **page_context,
            "page_title": "Doanh thu theo ngày",
            "page_description": (
                "Tổng hợp giá trị booking theo ngày trả phòng, số tiền đã thu "
                "và công nợ còn lại."
            ),
            "report_mode": "daily",
            "summary": summary,
            "branches": branches,
            "filters": {
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "branchId": branch_id,
            },
        },
    )


@login_required
def revenue_monthly(request):
    if not can_view_revenue(request.user):
        raise PermissionDenied("Bạn không có quyền xem dữ liệu doanh thu.")

    current_year = timezone.localdate().year
    try:
        selected_year = int(request.GET.get("year", current_year))
    except (TypeError, ValueError):
        selected_year = current_year
    if selected_year < 2000 or selected_year > 2100:
        selected_year = current_year
    branch_id = str(request.GET.get("branchId") or "").strip()

    queryset, branches = _revenue_queryset_for_request(request, branch_id)
    period_start = date(selected_year, 1, 1)
    period_end = date(selected_year + 1, 1, 1)
    queryset = queryset.filter(
        checkout_at__gte=_local_day_start(period_start),
        checkout_at__lt=_local_day_start(period_end),
    )
    rows = _revenue_rows(
        queryset,
        TruncMonth("checkout_at", tzinfo=timezone.get_current_timezone()),
    )
    summary = _revenue_summary(queryset)
    summary["period_count"] = len(rows)
    page_context = paginate_context(
        request,
        rows,
        context_object_name="rows",
        per_page=20,
    )
    return render(
        request,
        "reservations/revenue_report.html",
        {
            **page_context,
            "page_title": "Doanh thu theo tháng",
            "page_description": (
                "Tổng hợp giá trị booking theo từng tháng trả phòng trong năm đã chọn."
            ),
            "report_mode": "monthly",
            "summary": summary,
            "branches": branches,
            "filters": {
                "year": str(selected_year),
                "branchId": branch_id,
            },
        },
    )


def _cost_scope(request, branch_id=""):
    if not can_view_revenue(request.user):
        raise PermissionDenied("Bạn không có quyền xem dữ liệu chi phí và vốn.")
    branches = revenue_branch_queryset(request.user)
    if not branch_id:
        return branches, None
    try:
        selected = branches.filter(pk=branch_id).first()
    except (ValidationError, ValueError):
        selected = None
    return branches, selected


def _cost_year(request):
    current_year = timezone.localdate().year
    try:
        year = int(request.GET.get("year", current_year))
    except (TypeError, ValueError):
        year = current_year
    return year if 2000 <= year <= 2100 else current_year


def _cost_month_rows(capital_queryset, expense_queryset):
    capital_rows = {
        row["period"]: row["total"]
        for row in capital_queryset.annotate(
            period=TruncMonth("capital_date")
        ).values("period").annotate(total=Sum("amount"))
    }
    expense_rows = {
        row["period"]: row["total"]
        for row in expense_queryset.annotate(
            period=TruncMonth("expense_date")
        ).values("period").annotate(total=Sum("amount"))
    }
    periods = sorted(set(capital_rows) | set(expense_rows))
    return [
        {
            "period": period,
            "capital_total": capital_rows.get(period, MONEY_ZERO),
            "expense_total": expense_rows.get(period, MONEY_ZERO),
            "net_total": capital_rows.get(period, MONEY_ZERO) - expense_rows.get(period, MONEY_ZERO),
        }
        for period in periods
    ]


@login_required
def costs_dashboard(request):
    year = _cost_year(request)
    branch_id = str(request.GET.get("branchId") or "").strip()
    branches, selected_branch = _cost_scope(request, branch_id)
    branch_filter = {"branch": selected_branch} if selected_branch else {}
    if branch_id and selected_branch is None:
        capital_queryset = CapitalEntry.objects.none()
        expense_queryset = OperatingExpense.objects.none()
    else:
        capital_queryset = CapitalEntry.objects.filter(
            branch__in=branches,
            capital_date__year=year,
            **branch_filter,
        )
        expense_queryset = OperatingExpense.objects.filter(
            branch__in=branches,
            expense_date__year=year,
            **branch_filter,
        )
    summary = {
        "capital_total": capital_queryset.aggregate(
            total=_zero_money_sum(F("amount"))
        )["total"],
        "expense_total": expense_queryset.aggregate(
            total=_zero_money_sum(F("amount"))
        )["total"],
        "paid_expense_total": expense_queryset.filter(
            payment_status=OperatingExpense.PaymentStatus.PAID
        ).aggregate(total=_zero_money_sum(F("amount")))["total"],
        "planned_expense_total": expense_queryset.filter(
            payment_status=OperatingExpense.PaymentStatus.PLANNED
        ).aggregate(total=_zero_money_sum(F("amount")))["total"],
    }
    summary["net_cash"] = summary["capital_total"] - summary["paid_expense_total"]
    return render(
        request,
        "reservations/costs_dashboard.html",
        {
            "page_title": "Chi phí và vốn",
            "page_description": "Theo dõi vốn ban đầu và chi phí vận hành theo chi nhánh.",
            "summary": summary,
            "rows": _cost_month_rows(capital_queryset, expense_queryset),
            "branches": branches,
            "filters": {"year": str(year), "branchId": branch_id},
        },
    )


@login_required
def profit_dashboard(request):
    year = _cost_year(request)
    branch_id = str(request.GET.get("branchId") or "").strip()
    branches, selected_branch = _cost_scope(request, branch_id)
    if branch_id and selected_branch is None:
        revenue_queryset = Booking.objects.none()
        expense_queryset = OperatingExpense.objects.none()
    else:
        branch_filter = {"branch": selected_branch} if selected_branch else {}
        revenue_queryset = Booking.objects.filter(
            branch__in=branches,
            checkout_at__year=year,
            checkout_at__isnull=False,
            **branch_filter,
        ).exclude(status=Booking.Status.CANCELLED)
        expense_queryset = OperatingExpense.objects.filter(
            branch__in=branches,
            expense_date__year=year,
            payment_status=OperatingExpense.PaymentStatus.PAID,
            **branch_filter,
        )
    revenue_total = revenue_queryset.aggregate(
        total=_zero_money_sum(_booking_total_expression())
    )["total"]
    expense_total = expense_queryset.aggregate(
        total=_zero_money_sum(F("amount"))
    )["total"]
    profit_total = revenue_total - expense_total
    profit_margin = (profit_total * Decimal("100") / revenue_total) if revenue_total else Decimal("0")

    revenue_rows = {
        row["period"].date() if hasattr(row["period"], "date") else row["period"]: row["total"]
        for row in revenue_queryset.annotate(
            period=TruncMonth("checkout_at", tzinfo=timezone.get_current_timezone())
        ).values("period").annotate(total=_zero_money_sum(_booking_total_expression()))
    }
    expense_rows = {
        row["period"].date() if hasattr(row["period"], "date") else row["period"]: row["total"]
        for row in expense_queryset.annotate(
            period=TruncMonth("expense_date")
        ).values("period").annotate(total=_zero_money_sum(F("amount")))
    }
    periods = sorted(set(revenue_rows) | set(expense_rows))
    rows = [
        {
            "period": period,
            "revenue_total": revenue_rows.get(period, MONEY_ZERO),
            "expense_total": expense_rows.get(period, MONEY_ZERO),
            "profit_total": revenue_rows.get(period, MONEY_ZERO) - expense_rows.get(period, MONEY_ZERO),
        }
        for period in periods
    ]
    return render(
        request,
        "reservations/profit_dashboard.html",
        {
            "page_title": "Lợi nhuận",
            "page_description": "Doanh thu booking trừ chi phí vận hành đã chi theo kỳ.",
            "summary": {
                "revenue_total": revenue_total,
                "expense_total": expense_total,
                "profit_total": profit_total,
                "profit_margin": profit_margin,
            },
            "rows": rows,
            "branches": branches,
            "filters": {"year": str(year), "branchId": branch_id},
        },
    )


@login_required
def capital_list(request):
    branch_id = str(request.GET.get("branchId") or "").strip()
    branches, selected_branch = _cost_scope(request, branch_id)
    queryset = CapitalEntry.objects.filter(branch__in=branches).select_related("branch")
    if branch_id:
        queryset = queryset.filter(branch=selected_branch) if selected_branch else queryset.none()
    query = str(request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(source__icontains=query) | Q(notes__icontains=query))
    from_date = parse_date(str(request.GET.get("from_date") or ""))
    to_date = parse_date(str(request.GET.get("to_date") or ""))
    if from_date:
        queryset = queryset.filter(capital_date__gte=from_date)
    if to_date:
        queryset = queryset.filter(capital_date__lte=to_date)
    context = paginate_context(
        request,
        queryset.order_by("-capital_date", "-created_at"),
        context_object_name="capital_entries",
        per_page=20,
    )
    return render(
        request,
        "reservations/capital_list.html",
        {
            **context,
            "branches": branches,
            "filters": {
                "q": query,
                "from_date": from_date.isoformat() if from_date else "",
                "to_date": to_date.isoformat() if to_date else "",
                "branchId": branch_id,
            },
        },
    )


@login_required
def capital_create(request):
    _cost_scope(request)
    form = CapitalEntryForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.created_by = request.user
        entry.updated_by = request.user
        entry.save()
        messages.success(request, "Đã ghi nhận vốn ban đầu.")
        return redirect("reservations:capital-list")
    return render(request, "reservations/cost_form.html", {"form": form, "form_title": "Thêm vốn ban đầu", "form_description": "Ghi nhận một khoản vốn theo chi nhánh.", "back_url": "reservations:capital-list"})


@login_required
def capital_update(request, entry_id):
    branches, _ = _cost_scope(request)
    entry = get_object_or_404(CapitalEntry.objects.filter(branch__in=branches), pk=entry_id)
    form = CapitalEntryForm(request.POST or None, instance=entry, user=request.user)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.updated_by = request.user
        entry.save()
        messages.success(request, "Đã cập nhật vốn ban đầu.")
        return redirect("reservations:capital-list")
    return render(request, "reservations/cost_form.html", {"form": form, "form_title": "Cập nhật vốn ban đầu", "form_description": entry.title, "back_url": "reservations:capital-list"})


@login_required
def expense_list(request):
    branch_id = str(request.GET.get("branchId") or "").strip()
    branches, selected_branch = _cost_scope(request, branch_id)
    queryset = OperatingExpense.objects.filter(branch__in=branches).select_related("branch")
    if branch_id:
        queryset = queryset.filter(branch=selected_branch) if selected_branch else queryset.none()
    query = str(request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(category__icontains=query) | Q(notes__icontains=query))
    status = str(request.GET.get("payment_status") or "").strip()
    if status in OperatingExpense.PaymentStatus.values:
        queryset = queryset.filter(payment_status=status)
    from_date = parse_date(str(request.GET.get("from_date") or ""))
    to_date = parse_date(str(request.GET.get("to_date") or ""))
    if from_date:
        queryset = queryset.filter(expense_date__gte=from_date)
    if to_date:
        queryset = queryset.filter(expense_date__lte=to_date)
    context = paginate_context(request, queryset.order_by("-expense_date", "-created_at"), context_object_name="expenses", per_page=20)
    return render(request, "reservations/expense_list.html", {**context, "branches": branches, "statuses": OperatingExpense.PaymentStatus.choices, "filters": {"q": query, "payment_status": status, "from_date": from_date.isoformat() if from_date else "", "to_date": to_date.isoformat() if to_date else "", "branchId": branch_id}})


@login_required
def expense_create(request):
    _cost_scope(request)
    form = OperatingExpenseForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.created_by = request.user
        expense.updated_by = request.user
        expense.save()
        messages.success(request, "Đã ghi nhận chi phí vận hành.")
        return redirect("reservations:expense-list")
    return render(request, "reservations/cost_form.html", {"form": form, "form_title": "Thêm chi phí vận hành", "form_description": "Ghi nhận điện nước, vật tư, sửa chữa hoặc khoản chi khác.", "back_url": "reservations:expense-list"})


@login_required
def expense_update(request, expense_id):
    branches, _ = _cost_scope(request)
    expense = get_object_or_404(OperatingExpense.objects.filter(branch__in=branches), pk=expense_id)
    form = OperatingExpenseForm(request.POST or None, instance=expense, user=request.user)
    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        expense.updated_by = request.user
        expense.save()
        messages.success(request, "Đã cập nhật chi phí vận hành.")
        return redirect("reservations:expense-list")
    return render(request, "reservations/cost_form.html", {"form": form, "form_title": "Cập nhật chi phí vận hành", "form_description": expense.name, "back_url": "reservations:expense-list"})
