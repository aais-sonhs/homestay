from datetime import date
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from common.list_views import paginate_collection, paginate_context
from housekeeping.services import request_context
from organizations.selectors import branch_queryset_for_user
from reservations.selectors import can_create_any_booking

from .forms import RoomAssetForm, RoomOperationsActionForm, RoomStopSellCreateForm
from .models import RoomAsset, RoomBlocker, RoomStopSell
from .selectors import (
    OPEN_STOP_SELL_STATUSES,
    blocker_queryset_for_user,
    build_daily_schedule,
    build_readiness_board,
    build_room_profile,
    can_manage_any_room_sales_status,
    can_manage_room_sales_status,
    room_sales_management_branch_queryset,
    stop_sell_queryset_for_user,
)
from .services import (
    RoomOperationsError,
    cancel_scheduled_stop_sell,
    confirm_room_blocker_clearance,
    confirm_room_reopen,
    create_room_stop_sell,
    request_room_reopen,
)


def _selected_date(request):
    try:
        return date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        return timezone.localdate()


def _branch_filter(request, branches):
    value = str(request.GET.get("branchId") or "")
    try:
        if value and branches.filter(pk=value).exists():
            return value
    except (ValidationError, ValueError):
        pass
    return None


@login_required
def operations_schedule(request):
    branches = branch_queryset_for_user(request.user)
    branch_id = _branch_filter(request, branches)
    selected_date = _selected_date(request)
    schedule = build_daily_schedule(request.user, selected_date, branch_id=branch_id)
    schedule_pagination = paginate_collection(
        request,
        schedule["rows"],
        per_page=20,
        page_parameter="schedule_page",
    )
    standalone_pagination = paginate_collection(
        request,
        schedule["standaloneTasks"],
        per_page=20,
        page_parameter="standalone_page",
    )
    schedule = {
        **schedule,
        "rows": schedule_pagination["items"],
        "standaloneTasks": standalone_pagination["items"],
    }
    return render(
        request,
        "room_operations/schedule.html",
        {
            "branches": branches,
            "selected_date": selected_date,
            "selected_branch_id": branch_id,
            "schedule": schedule,
            "schedule_pagination": schedule_pagination,
            "standalone_pagination": standalone_pagination,
            "can_create_booking": can_create_any_booking(request.user),
        },
    )


@login_required
def room_readiness_board(request):
    branches = branch_queryset_for_user(request.user)
    branch_id = _branch_filter(request, branches)
    query = str(request.GET.get("q") or "").strip()
    board = build_readiness_board(
        request.user,
        branch_id=branch_id,
        query=query,
        state=request.GET.get("state", ""),
    )
    page_context = paginate_context(
        request,
        board["rows"],
        context_object_name="readiness_rows",
        per_page=18,
    )
    board = {**board, "rows": page_context["readiness_rows"]}
    base_url = reverse("room_operations:room-readiness")

    def summary_url(state=""):
        params = {}
        if branch_id:
            params["branchId"] = branch_id
        if query:
            params["q"] = query
        if state:
            params["state"] = state
        return f"{base_url}?{urlencode(params)}" if params else base_url

    return render(
        request,
        "room_operations/readiness_board.html",
        {
            "branches": branches,
            "selected_branch_id": branch_id,
            "state_choices": (
                ("", "Mọi trạng thái"),
                ("READY", "Sẵn sàng"),
                ("OCCUPIED", "Đang có khách"),
                ("NOT_READY", "Chưa sẵn sàng"),
                ("BLOCKED", "Đang bị chặn"),
                ("CHECKIN_RISK", "Rủi ro check-in"),
                ("STOP_SELL", "Đang dừng bán"),
            ),
            "summary_links": {
                "total": summary_url(),
                "ready": summary_url("READY"),
                "occupied": summary_url("OCCUPIED"),
                "not_ready": summary_url("NOT_READY"),
                "blocked": summary_url("BLOCKED"),
                "checkin_risk": summary_url("CHECKIN_RISK"),
                "stop_sell": summary_url("STOP_SELL"),
            },
            "board": board,
            **page_context,
        },
    )


@login_required
def room_profile(request, room_id):
    profile = build_room_profile(request.user, room_id)
    if profile is None:
        raise Http404("Không tìm thấy phòng trong phạm vi được cấp.")
    return render(request, "room_operations/room_profile.html", profile)


@login_required
def asset_list(request):
    branches = room_sales_management_branch_queryset(request.user)
    if not branches.exists():
        raise PermissionDenied("Bạn không có quyền xem danh mục tài sản.")
    queryset = RoomAsset.objects.filter(branch__in=branches).select_related("branch", "room")
    branch_id = str(request.GET.get("branchId") or "").strip()
    if branch_id:
        try:
            branch_allowed = branches.filter(pk=branch_id).exists()
        except (ValidationError, ValueError):
            branch_allowed = False
        queryset = queryset.filter(branch_id=branch_id) if branch_allowed else queryset.none()
    query = str(request.GET.get("q") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(serial_number__icontains=query)
            | Q(room__code__icontains=query)
        )
    status = str(request.GET.get("status") or "").strip()
    if status in RoomAsset.Status.values:
        queryset = queryset.filter(status=status)
    maintenance_due = request.GET.get("maintenanceDue") == "true"
    if maintenance_due:
        queryset = queryset.filter(
            is_active=True,
            next_maintenance_at__isnull=False,
            next_maintenance_at__lte=timezone.localdate(),
        )
    page_context = paginate_context(
        request,
        queryset.order_by("branch__name", "room__code", "code"),
        context_object_name="assets",
        per_page=24,
    )
    return render(
        request,
        "room_operations/asset_list.html",
        {
            **page_context,
            "branches": branches,
            "statuses": RoomAsset.Status.choices,
            "filters": {
                "q": query,
                "branchId": branch_id,
                "status": status,
                "maintenanceDue": maintenance_due,
            },
            "today": timezone.localdate(),
        },
    )


@login_required
def asset_create(request):
    if not can_manage_any_room_sales_status(request.user):
        raise PermissionDenied("Bạn không có quyền tạo tài sản.")
    form = RoomAssetForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        asset = form.save()
        messages.success(request, f"Đã thêm tài sản {asset.code}.")
        return redirect("room_operations:asset-list")
    return render(
        request,
        "room_operations/asset_form.html",
        {"form": form, "form_title": "Thêm thiết bị / tài sản"},
    )


@login_required
def asset_update(request, asset_id):
    branches = room_sales_management_branch_queryset(request.user)
    asset = get_object_or_404(
        RoomAsset.objects.select_related("branch", "room").filter(branch__in=branches),
        pk=asset_id,
    )
    if not can_manage_room_sales_status(request.user, asset.branch):
        raise PermissionDenied("Bạn không có quyền cập nhật tài sản này.")
    form = RoomAssetForm(request.POST or None, instance=asset, user=request.user)
    if request.method == "POST" and form.is_valid():
        asset = form.save()
        messages.success(request, f"Đã cập nhật tài sản {asset.code}.")
        return redirect("room_operations:asset-list")
    return render(
        request,
        "room_operations/asset_form.html",
        {"form": form, "form_title": f"Cập nhật tài sản {asset.code}", "asset": asset},
    )


@login_required
def stop_sell_list(request):
    branches = branch_queryset_for_user(request.user)
    queryset = stop_sell_queryset_for_user(request.user)
    query = str(request.GET.get("q") or "").strip()
    status = str(request.GET.get("status") or "").strip()
    branch_id = str(request.GET.get("branchId") or "").strip()
    selected_date = str(request.GET.get("date") or "").strip()
    if query:
        queryset = queryset.filter(
            Q(room__code__icontains=query)
            | Q(room__name__icontains=query)
            | Q(reason__icontains=query)
            | Q(blocker__reason__icontains=query)
        )
    if status in RoomStopSell.Status.values:
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
            messages.error(request, "Ngày lọc stop-sell không hợp lệ.")
        else:
            queryset = queryset.filter(starts_at__date__lte=day, planned_end_at__date__gte=day)
    page_context = paginate_context(
        request,
        queryset.order_by("-starts_at", "room__code"),
        context_object_name="stop_sells",
        per_page=20,
    )
    stop_sell_rows = [
        {
            "stopSell": stop_sell,
            "canManage": can_manage_room_sales_status(request.user, stop_sell.branch),
            "isFuture": stop_sell.starts_at > timezone.now(),
            "actionForm": RoomOperationsActionForm(initial={"version": stop_sell.version}),
        }
        for stop_sell in page_context["stop_sells"]
    ]
    pending_blocker_queryset = (
        blocker_queryset_for_user(request.user)
        .filter(status=RoomBlocker.Status.CLEARANCE_PENDING)
        .exclude(stop_sells__status__in=OPEN_STOP_SELL_STATUSES)
        .distinct()
        .order_by("branch__name", "room__code")
    )
    blocker_pagination = paginate_collection(
        request,
        pending_blocker_queryset,
        per_page=20,
        page_parameter="blocker_page",
    )
    pending_blockers = blocker_pagination["items"]
    pending_blocker_rows = [
        {
            "blocker": blocker,
            "canManage": can_manage_room_sales_status(request.user, blocker.branch),
        }
        for blocker in pending_blockers
    ]
    return render(
        request,
        "room_operations/stop_sell_list.html",
        {
            **page_context,
            "stop_sell_rows": stop_sell_rows,
            "pending_blockers": pending_blockers,
            "pending_blocker_rows": pending_blocker_rows,
            "blocker_pagination": blocker_pagination,
            "branches": branches,
            "statuses": RoomStopSell.Status.choices,
            "filters": {
                "q": query,
                "status": status,
                "branchId": branch_id,
                "date": selected_date,
            },
            "can_manage_stop_sell": can_manage_any_room_sales_status(request.user),
        },
    )


@login_required
def stop_sell_create(request):
    if not can_manage_any_room_sales_status(request.user):
        raise PermissionDenied("Bạn không có quyền tạo khoảng dừng bán.")
    initial = {}
    if request.GET.get("roomId"):
        initial["room"] = request.GET["roomId"]
    if request.GET.get("branchId"):
        initial["branch"] = request.GET["branchId"]
    form = RoomStopSellCreateForm(
        request.POST or None,
        user=request.user,
        initial=initial if not request.POST else None,
    )
    if request.method == "POST" and form.is_valid():
        try:
            stop_sell, affected_count = create_room_stop_sell(
                request.user,
                form.cleaned_data,
                request_context(request),
            )
        except RoomOperationsError as error:
            form.add_error(None, error.message)
        else:
            messages.success(
                request,
                f"Đã dừng bán phòng {stop_sell.room.code}; "
                f"{affected_count} booking hiện có giao với khoảng này.",
            )
            return redirect("room_operations:stop-sell-list")
    return render(
        request,
        "room_operations/stop_sell_form.html",
        {"form": form},
    )


def _scoped_stop_sell_or_404(request, stop_sell_id):
    return get_object_or_404(stop_sell_queryset_for_user(request.user), pk=stop_sell_id)


def _validated_action_form(request):
    form = RoomOperationsActionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Vui lòng nhập phiên bản và ghi chú hợp lệ.")
        return None
    return form


@login_required
def stop_sell_request_reopen(request, stop_sell_id):
    if request.method != "POST":
        raise PermissionDenied("Thao tác yêu cầu mở lại cần phương thức POST.")
    stop_sell = _scoped_stop_sell_or_404(request, stop_sell_id)
    if not can_manage_room_sales_status(request.user, stop_sell.branch):
        raise PermissionDenied("Bạn chỉ có quyền xem trạng thái dừng bán.")
    form = _validated_action_form(request)
    if form is None:
        return redirect("room_operations:stop-sell-list")
    try:
        request_room_reopen(
            request.user,
            stop_sell.id,
            form.cleaned_data["version"],
            form.cleaned_data["note"],
            request_context(request),
        )
    except RoomOperationsError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"Đã gửi yêu cầu mở bán lại phòng {stop_sell.room.code}.")
    return redirect("room_operations:stop-sell-list")


@login_required
def stop_sell_confirm_reopen(request, stop_sell_id):
    if request.method != "POST":
        raise PermissionDenied("Thao tác xác nhận mở lại cần phương thức POST.")
    stop_sell = _scoped_stop_sell_or_404(request, stop_sell_id)
    if not can_manage_room_sales_status(request.user, stop_sell.branch):
        raise PermissionDenied("Bạn chỉ có quyền xem trạng thái dừng bán.")
    form = _validated_action_form(request)
    if form is None:
        return redirect("room_operations:stop-sell-list")
    try:
        confirm_room_reopen(
            request.user,
            stop_sell.id,
            form.cleaned_data["version"],
            form.cleaned_data["note"],
            request_context(request),
        )
    except RoomOperationsError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"Đã xác nhận mở bán lại phòng {stop_sell.room.code}.")
    return redirect("room_operations:stop-sell-list")


@login_required
def stop_sell_cancel(request, stop_sell_id):
    if request.method != "POST":
        raise PermissionDenied("Thao tác hủy lịch dừng bán cần phương thức POST.")
    stop_sell = _scoped_stop_sell_or_404(request, stop_sell_id)
    if not can_manage_room_sales_status(request.user, stop_sell.branch):
        raise PermissionDenied("Bạn chỉ có quyền xem trạng thái dừng bán.")
    form = _validated_action_form(request)
    if form is None:
        return redirect("room_operations:stop-sell-list")
    try:
        cancel_scheduled_stop_sell(
            request.user,
            stop_sell.id,
            form.cleaned_data["version"],
            form.cleaned_data["note"],
            request_context(request),
        )
    except RoomOperationsError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"Đã hủy lịch dừng bán phòng {stop_sell.room.code}.")
    return redirect("room_operations:stop-sell-list")


@login_required
def blocker_confirm_clearance(request, blocker_id):
    if request.method != "POST":
        raise PermissionDenied("Thao tác xác nhận gỡ blocker cần phương thức POST.")
    blocker = get_object_or_404(blocker_queryset_for_user(request.user), pk=blocker_id)
    if not can_manage_room_sales_status(request.user, blocker.branch):
        raise PermissionDenied("Bạn chỉ có quyền xem blocker.")
    form = _validated_action_form(request)
    if form is None:
        return redirect("room_operations:stop-sell-list")
    try:
        confirm_room_blocker_clearance(
            request.user,
            blocker.id,
            form.cleaned_data["version"],
            form.cleaned_data["note"],
            request_context(request),
        )
    except RoomOperationsError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"Đã gỡ blocker phòng {blocker.room.code}.")
    return redirect("room_operations:stop-sell-list")
