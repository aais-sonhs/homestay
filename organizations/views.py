from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.models import User
from common.list_views import paginate_context
from housekeeping.models import HousekeepingTask

from .forms import BranchForm, BranchOwnerForm
from .models import Branch
from .services import (
    BranchOperationError,
    assign_branches_to_owner,
    create_branch,
    set_branch_active,
    update_branch,
)


def _require_platform_admin(user):
    if not user.is_superuser:
        raise PermissionDenied("Chỉ Super Admin được quản lý chi nhánh và tài khoản chủ chi nhánh.")


@login_required
def branch_list(request):
    _require_platform_admin(request.user)
    query = str(request.GET.get("q") or "").strip()
    status = str(request.GET.get("status") or "active").strip()
    queryset = Branch.objects.select_related("owner").annotate(
        room_count=Count("rooms", distinct=True),
        member_count=Count("memberships", distinct=True),
        open_task_count=Count(
            "housekeeping_tasks",
            filter=~Q(
                housekeeping_tasks__status__in={
                    HousekeepingTask.Status.QC_APPROVED,
                    HousekeepingTask.Status.CANCELLED,
                }
            ),
            distinct=True,
        ),
    ).order_by("name", "code")
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query) | Q(name__icontains=query) | Q(address__icontains=query)
        )
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)
    context = {
        "filters": {"q": query, "status": status},
        **paginate_context(request, queryset, context_object_name="branches", per_page=20),
    }
    return render(request, "organizations/branch_list.html", context)


@login_required
def branch_create(request):
    _require_platform_admin(request.user)
    form = BranchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        branch = create_branch(**form.cleaned_data, changed_by=request.user)
        messages.success(request, f"Đã tạo chi nhánh {branch.name} và cấu hình vận hành mặc định.")
        return redirect("organizations:branch-list")
    return render(
        request,
        "organizations/branch_form.html",
        {
            "form": form,
            "page_title": "Thêm chi nhánh",
            "page_description": "Tạo cơ sở lưu trú mới trong hệ thống Bliss Home.",
            "submit_label": "Tạo chi nhánh",
        },
    )


@login_required
def branch_update(request, branch_id):
    _require_platform_admin(request.user)
    branch = get_object_or_404(Branch, pk=branch_id)
    form = BranchForm(request.POST or None, instance=branch)
    if request.method == "POST" and form.is_valid():
        branch = update_branch(branch, **form.cleaned_data, changed_by=request.user)
        messages.success(request, f"Đã cập nhật chi nhánh {branch.name}.")
        return redirect("organizations:branch-list")
    return render(
        request,
        "organizations/branch_form.html",
        {
            "form": form,
            "branch": branch,
            "page_title": f"Chỉnh sửa {branch.name}",
            "page_description": "Cập nhật mã, tên và địa chỉ chi nhánh.",
            "submit_label": "Lưu thay đổi",
            "ownership_history": branch.ownership_history.select_related(
                "previous_owner", "new_owner", "changed_by"
            )[:20],
        },
    )


@login_required
def branch_toggle_active(request, branch_id):
    _require_platform_admin(request.user)
    if request.method != "POST":
        raise PermissionDenied("Thao tác thay đổi trạng thái yêu cầu phương thức POST.")
    branch = get_object_or_404(Branch, pk=branch_id)
    activate = request.POST.get("active") == "true"
    try:
        updated = set_branch_active(branch, active=activate)
    except BranchOperationError as error:
        messages.error(request, str(error))
    else:
        action = "kích hoạt lại" if updated.is_active else "ngừng hoạt động"
        messages.success(request, f"Đã {action} chi nhánh {updated.name}.")
    return redirect("organizations:branch-list")


@login_required
def branch_owner_list(request):
    _require_platform_admin(request.user)
    query = str(request.GET.get("q") or "").strip()
    status = str(request.GET.get("status") or "active").strip()
    queryset = (
        User.objects.filter(role=User.Role.BRANCH_OWNER, is_deleted=False)
        .annotate(
            branch_count=Count("owned_branches", distinct=True),
            active_branch_count=Count(
                "owned_branches",
                filter=Q(owned_branches__is_active=True),
                distinct=True,
            ),
        )
        .prefetch_related("owned_branches")
        .order_by("first_name", "last_name", "username")
    )
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone_number__icontains=query)
            | Q(owned_branches__name__icontains=query)
            | Q(owned_branches__code__icontains=query)
        ).distinct()
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)
    elif status == "unassigned":
        queryset = queryset.filter(owned_branches__isnull=True)
    context = {
        "filters": {"q": query, "status": status},
        **paginate_context(request, queryset, context_object_name="owners", per_page=20),
    }
    return render(request, "organizations/branch_owner_list.html", context)


@login_required
def branch_owner_create(request):
    _require_platform_admin(request.user)
    form = BranchOwnerForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            owner = form.save()
            transferred = assign_branches_to_owner(
                owner=owner,
                branches=form.cleaned_data["assign_branches"],
                changed_by=request.user,
            )
        suffix = f" và giao {transferred} chi nhánh" if transferred else ""
        messages.success(
            request,
            f"Đã tạo tài khoản chủ chi nhánh {owner.display_name}{suffix}.",
        )
        return redirect("organizations:branch-owner-list")
    return render(
        request,
        "organizations/branch_owner_form.html",
        {
            "form": form,
            "page_title": "Thêm chủ chi nhánh",
            "page_description": "Tạo tài khoản chủ để gán khi thêm hoặc chỉnh sửa chi nhánh.",
            "submit_label": "Tạo tài khoản",
        },
    )


@login_required
def branch_owner_update(request, owner_id):
    _require_platform_admin(request.user)
    owner = get_object_or_404(
        User,
        pk=owner_id,
        role=User.Role.BRANCH_OWNER,
        is_deleted=False,
    )
    form = BranchOwnerForm(request.POST or None, instance=owner)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            owner = form.save()
            transferred = assign_branches_to_owner(
                owner=owner,
                branches=form.cleaned_data["assign_branches"],
                changed_by=request.user,
            )
        suffix = f" và giao {transferred} chi nhánh" if transferred else ""
        messages.success(request, f"Đã cập nhật tài khoản {owner.display_name}{suffix}.")
        return redirect("organizations:branch-owner-list")
    return render(
        request,
        "organizations/branch_owner_form.html",
        {
            "form": form,
            "owner": owner,
            "page_title": f"Chỉnh sửa {owner.display_name}",
            "page_description": "Cập nhật tài khoản và gán các chi nhánh được phép quản lý.",
            "submit_label": "Lưu thay đổi",
        },
    )
