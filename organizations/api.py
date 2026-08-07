import secrets
import uuid

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from accounts.identifiers import normalize_email, normalize_phone
from accounts.models import User
from accounts.services import password_policy_errors
from common.api_auth import api_authenticated
from housekeeping.api.errors import APIError, api_endpoint, parse_json, success_response

from .models import Branch, BranchMembership


ROLE_DEFINITIONS = {
    "manager": {
        "label": "Quản lý",
        "user_role": User.Role.MANAGER,
        "membership_role": BranchMembership.MembershipRole.MANAGER,
        "can_manage_team": True,
        "owner_only": True,
    },
    "housekeeping_lead": {
        "label": "Trưởng nhóm buồng phòng",
        "user_role": User.Role.HOUSEKEEPING,
        "membership_role": BranchMembership.MembershipRole.HOUSEKEEPING_LEAD,
        "can_manage_team": True,
        "owner_only": False,
    },
    "housekeeping": {
        "label": "Nhân viên buồng phòng",
        "user_role": User.Role.HOUSEKEEPING,
        "membership_role": BranchMembership.MembershipRole.HOUSEKEEPER,
        "can_manage_team": False,
        "owner_only": False,
    },
    "qc": {
        "label": "Kiểm tra chất lượng",
        "user_role": User.Role.QC,
        "membership_role": BranchMembership.MembershipRole.QC,
        "can_manage_team": False,
        "owner_only": False,
    },
    "technician": {
        "label": "Kỹ thuật",
        "user_role": User.Role.TECHNICIAN,
        "membership_role": BranchMembership.MembershipRole.TECHNICIAN,
        "can_manage_team": False,
        "owner_only": False,
    },
    "warehouse": {
        "label": "Kho",
        "user_role": User.Role.WAREHOUSE,
        "membership_role": BranchMembership.MembershipRole.WAREHOUSE,
        "can_manage_team": False,
        "owner_only": False,
    },
    "customer_service": {
        "label": "Chăm sóc khách hàng",
        "user_role": User.Role.CUSTOMER_SERVICE,
        "membership_role": BranchMembership.MembershipRole.VIEWER,
        "can_manage_team": False,
        "owner_only": False,
    },
    "sales": {
        "label": "Kinh doanh",
        "user_role": User.Role.SALES,
        "membership_role": BranchMembership.MembershipRole.SALES,
        "can_manage_team": False,
        "owner_only": False,
    },
}


def _can_open_staff_management(user):
    return bool(
        not user.is_superuser
        and user.role in {User.Role.BRANCH_OWNER, User.Role.MANAGER}
    )


def _manageable_branches(user):
    queryset = Branch.objects.filter(is_active=True)
    if user.role == User.Role.BRANCH_OWNER:
        return queryset.filter(owner=user).order_by("name", "code")
    if user.role == User.Role.MANAGER:
        return queryset.filter(
            memberships__user=user,
            memberships__is_active=True,
        ).filter(
            Q(memberships__membership_role=BranchMembership.MembershipRole.MANAGER)
            | Q(memberships__can_manage_team=True)
        ).distinct().order_by("name", "code")
    return queryset.none()


def _can_create_manager(user, branch):
    return bool(
        not user.is_superuser
        and user.role == User.Role.BRANCH_OWNER
        and branch.owner_id == user.id
    )


def _role_options(user, branch=None):
    options = []
    for key, definition in ROLE_DEFINITIONS.items():
        if definition["owner_only"] and branch is not None and not _can_create_manager(user, branch):
            continue
        options.append({"key": key, "label": definition["label"]})
    return options


def _role_key(membership):
    if membership.membership_role == BranchMembership.MembershipRole.HOUSEKEEPING_LEAD:
        return "housekeeping_lead"
    if (
        membership.membership_role == BranchMembership.MembershipRole.VIEWER
        and membership.user.role == User.Role.CUSTOMER_SERVICE
    ):
        return "customer_service"
    for key, definition in ROLE_DEFINITIONS.items():
        if (
            definition["user_role"] == membership.user.role
            and definition["membership_role"] == membership.membership_role
        ):
            return key
    return membership.membership_role.lower()


def _staff_item(membership):
    role_key = _role_key(membership)
    role_definition = ROLE_DEFINITIONS.get(role_key)
    return {
        "membershipId": membership.id,
        "userId": membership.user_id,
        "name": membership.user.display_name,
        "email": membership.user.email,
        "phoneNumber": membership.user.phone_number,
        "roleKey": role_key,
        "roleLabel": (
            role_definition["label"]
            if role_definition
            else membership.get_membership_role_display()
        ),
        "isActive": bool(membership.is_active and membership.user.is_active),
        "branch": {
            "id": str(membership.branch_id),
            "code": membership.branch.code,
            "name": membership.branch.name,
        },
    }


def _unique_staff_username():
    while True:
        candidate = f"bh_{secrets.token_hex(8)}"
        if not User.objects.filter(username=candidate).exists():
            return candidate


def _validated_identity(payload):
    full_name = str(payload.get("fullName") or "").strip()
    if len(full_name) < 2 or len(full_name) > 150:
        raise APIError("FULL_NAME_INVALID", "Họ và tên phải có từ 2 đến 150 ký tự.")
    try:
        email = normalize_email(payload.get("email"))
    except ValidationError:
        raise APIError("EMAIL_INVALID", "Thư điện tử không đúng định dạng.") from None
    try:
        phone = normalize_phone(payload.get("phoneNumber"))
    except ValidationError:
        raise APIError("PHONE_INVALID", "Số điện thoại không đúng định dạng.") from None
    return full_name, email, phone


def _branch_from_payload(user, payload):
    try:
        branch_id = uuid.UUID(str(payload.get("branchId") or ""))
    except (ValueError, TypeError, AttributeError):
        raise APIError("BRANCH_INVALID", "Vui lòng chọn chi nhánh.") from None
    branch = _manageable_branches(user).filter(pk=branch_id).first()
    if branch is None:
        raise APIError(
            "BRANCH_NOT_ALLOWED",
            "Bạn không có quyền quản lý nhân sự tại chi nhánh này.",
            status=403,
        )
    return branch


def _create_staff(request):
    payload = parse_json(request)
    branch = _branch_from_payload(request.user, payload)
    role_key = str(payload.get("roleKey") or "").strip()
    definition = ROLE_DEFINITIONS.get(role_key)
    if definition is None:
        raise APIError("STAFF_ROLE_INVALID", "Vai trò nhân viên không hợp lệ.")
    if definition["owner_only"] and not _can_create_manager(request.user, branch):
        raise APIError(
            "STAFF_ROLE_NOT_ALLOWED",
            "Chỉ Chủ chi nhánh hoặc Founder được tạo tài khoản Quản lý.",
            status=403,
        )

    full_name, email, phone = _validated_identity(payload)
    password = str(payload.get("password") or "")
    confirm_password = str(payload.get("confirmPassword") or "")
    if password != confirm_password:
        raise APIError("PASSWORD_NOT_MATCH", "Xác nhận mật khẩu không khớp.")

    user = User(
        username=_unique_staff_username(),
        first_name=full_name,
        email=email,
        phone_number=phone,
        normalized_phone=phone,
        role=definition["user_role"],
        is_active=True,
        is_staff=False,
        is_superuser=False,
        password_changed_at=timezone.now(),
    )
    errors = password_policy_errors(password, user)
    if errors:
        raise APIError(
            "PASSWORD_POLICY_FAILED",
            errors[0],
            details={"errors": errors},
        )

    try:
        with transaction.atomic():
            if User.objects.filter(email__iexact=email).exists():
                raise APIError(
                    "EMAIL_ALREADY_REGISTERED",
                    "Thư điện tử này đã được sử dụng.",
                    status=409,
                )
            if User.objects.filter(normalized_phone=phone).exists():
                raise APIError(
                    "PHONE_ALREADY_REGISTERED",
                    "Số điện thoại này đã được sử dụng.",
                    status=409,
                )
            user.set_password(password)
            user.save()
            membership = BranchMembership.objects.create(
                user=user,
                branch=branch,
                membership_role=definition["membership_role"],
                can_manage_team=definition["can_manage_team"],
                is_active=True,
            )
    except IntegrityError:
        raise APIError(
            "ACCOUNT_ALREADY_REGISTERED",
            "Thư điện tử hoặc số điện thoại này đã được sử dụng.",
            status=409,
        ) from None

    membership = BranchMembership.objects.select_related("user", "branch").get(pk=membership.pk)
    return success_response(
        request,
        {
            "accountCreated": True,
            "staff": _staff_item(membership),
            "message": f"Đã tạo tài khoản {user.display_name} tại {branch.name}.",
        },
        status=201,
    )


def _list_staff(request):
    branches = list(_manageable_branches(request.user))
    branch_ids = [branch.id for branch in branches]
    selected_branch_id = str(request.GET.get("branchId") or "").strip()
    if selected_branch_id:
        try:
            selected_branch_uuid = uuid.UUID(selected_branch_id)
        except ValueError:
            raise APIError("BRANCH_INVALID", "Chi nhánh lọc không hợp lệ.") from None
        if selected_branch_uuid not in branch_ids:
            raise APIError(
                "BRANCH_NOT_ALLOWED",
                "Bạn không có quyền xem nhân sự tại chi nhánh này.",
                status=403,
            )
        branch_ids = [selected_branch_uuid]

    memberships = (
        BranchMembership.objects.select_related("user", "branch")
        .filter(branch_id__in=branch_ids, user__is_deleted=False)
        .exclude(user__role__in={User.Role.FOUNDER, User.Role.BRANCH_OWNER})
        .order_by("branch__name", "user__first_name", "user__username")
    )
    query = str(request.GET.get("q") or "").strip()
    if query:
        memberships = memberships.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__email__icontains=query)
            | Q(user__phone_number__icontains=query)
        )

    counts = {}
    for branch_id, count in (
        BranchMembership.objects.filter(
            branch_id__in=[branch.id for branch in branches],
            is_active=True,
            user__is_active=True,
            user__is_deleted=False,
        )
        .exclude(user__role__in={User.Role.FOUNDER, User.Role.BRANCH_OWNER})
        .values_list("branch_id")
        .annotate(total=Count("id"))
    ):
        counts[branch_id] = count

    return success_response(
        request,
        {
            "branches": [
                {
                    "id": str(branch.id),
                    "code": branch.code,
                    "name": branch.name,
                    "staffCount": counts.get(branch.id, 0),
                    "canCreateManager": _can_create_manager(request.user, branch),
                }
                for branch in branches
            ],
            "roleOptions": _role_options(request.user),
            "items": [_staff_item(membership) for membership in memberships[:500]],
        },
    )


@api_endpoint("GET", "POST")
@api_authenticated
def staff_collection(request):
    if not _can_open_staff_management(request.user):
        raise APIError(
            "STAFF_MANAGEMENT_NOT_ALLOWED",
            (
                "Super Admin chỉ tạo tài khoản Chủ chi nhánh. "
                "Nhân sự cấp dưới do Chủ chi nhánh hoặc Quản lý phụ trách."
            ),
            status=403,
        )
    if request.method == "POST":
        return _create_staff(request)
    return _list_staff(request)
