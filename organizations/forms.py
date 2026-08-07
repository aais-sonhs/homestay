import re

from django import forms
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.identifiers import normalize_email, normalize_phone
from accounts.models import User
from accounts.services import password_policy_errors
from common.forms import StyledModelForm

from .models import Branch
from .models import BranchMembership
from .api import (
    ROLE_DEFINITIONS,
    _can_create_manager,
    _manageable_branches,
    _unique_staff_username,
)


class BranchAssignmentField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, branch):
        owner_name = branch.owner.display_name if branch.owner_id else "chưa có chủ"
        state = "đang hoạt động" if branch.is_active else "ngừng hoạt động"
        return f"{branch.code} — {branch.name} · hiện tại: {owner_name} · {state}"


class BranchForm(StyledModelForm):
    class Meta:
        model = Branch
        fields = ("code", "name", "address", "owner")
        labels = {
            "code": "Mã chi nhánh",
            "name": "Tên chi nhánh",
            "address": "Địa chỉ",
            "owner": "Chủ chi nhánh",
        }
        help_texts = {
            "code": "Dùng mã ngắn, không dấu; ví dụ DALAT hoặc HCM-Q1.",
            "name": "Tên hiển thị cho người dùng trên lịch và báo cáo.",
            "owner": "Mỗi chi nhánh có một chủ. Tạo tài khoản chủ trước nếu danh sách chưa có.",
        }
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "Ví dụ: DALAT"}),
            "name": forms.TextInput(attrs={"placeholder": "Ví dụ: Bliss Home Đà Lạt"}),
            "address": forms.Textarea(attrs={"rows": 3, "placeholder": "Địa chỉ đầy đủ của chi nhánh"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        owner_ids = []
        if self.instance and self.instance.owner_id:
            owner_ids.append(self.instance.owner_id)
        self.fields["owner"].required = True
        self.fields["owner"].empty_label = "Chọn tài khoản chủ chi nhánh"
        self.fields["owner"].queryset = User.objects.filter(
            Q(role=User.Role.BRANCH_OWNER, is_active=True, is_deleted=False)
            | Q(pk__in=owner_ids)
        ).order_by("first_name", "last_name", "username")

    def clean_code(self):
        code = str(self.cleaned_data.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", code):
            raise forms.ValidationError("Mã chỉ gồm chữ cái không dấu, số, dấu gạch ngang hoặc gạch dưới.")
        duplicates = Branch.objects.filter(code__iexact=code)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Mã chi nhánh đã tồn tại.")
        return code

    def clean_name(self):
        return str(self.cleaned_data.get("name") or "").strip()

    def clean_address(self):
        return str(self.cleaned_data.get("address") or "").strip()


class BranchOwnerForm(StyledModelForm):
    assign_branches = BranchAssignmentField(
        label="Gán hoặc chuyển chi nhánh",
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": "branch-assignment-options"}),
        help_text=(
            "Chọn các chi nhánh cần giao cho tài khoản này. Nếu chi nhánh đã có chủ, "
            "hệ thống sẽ chuyển chủ và lưu lịch sử audit."
        ),
    )
    password = forms.CharField(
        label="Mật khẩu",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Tối thiểu 8 ký tự, có chữ hoa, chữ thường, số và ký tự đặc biệt.",
    )
    confirm_password = forms.CharField(
        label="Xác nhận mật khẩu",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = (
            "username",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "is_active",
            "password",
            "confirm_password",
        )
        labels = {
            "username": "Tên đăng nhập",
            "first_name": "Tên",
            "last_name": "Họ và tên đệm",
            "email": "Thư điện tử",
            "phone_number": "Số điện thoại",
            "is_active": "Cho phép đăng nhập",
        }
        help_texts = {
            "username": "Dùng để đăng nhập hệ thống; không nên thay đổi sau khi đã bàn giao.",
            "is_active": "Không thể khóa tài khoản đang sở hữu chi nhánh hoạt động.",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "owner@example.com"}),
            "phone_number": forms.TextInput(attrs={"placeholder": "Ví dụ: 0901234567"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        editing = bool(self.instance and self.instance.pk)
        branches = Branch.objects.select_related("owner").order_by("name", "code")
        if editing:
            branches = branches.exclude(owner=self.instance)
        self.fields["assign_branches"].queryset = branches
        self.fields["password"].required = not editing
        self.fields["confirm_password"].required = not editing
        if editing:
            self.fields["password"].help_text = "Để trống nếu không thay đổi mật khẩu."
        else:
            self.fields["is_active"].initial = True

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email") or "")
        if not email:
            raise forms.ValidationError("Vui lòng nhập thư điện tử của chủ chi nhánh.")
        duplicates = User.objects.filter(email__iexact=email, is_deleted=False)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Thư điện tử đã được sử dụng bởi tài khoản khác.")
        return email

    def clean_phone_number(self):
        raw_phone = str(self.cleaned_data.get("phone_number") or "").strip()
        if not raw_phone:
            return ""
        normalized = normalize_phone(raw_phone)
        duplicates = User.objects.filter(normalized_phone=normalized, is_deleted=False)
        if self.instance.pk:
            duplicates = duplicates.exclude(pk=self.instance.pk)
        if duplicates.exists():
            raise forms.ValidationError("Số điện thoại đã được sử dụng bởi tài khoản khác.")
        return raw_phone

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password") or ""
        confirmation = cleaned_data.get("confirm_password") or ""
        if password or confirmation:
            if password != confirmation:
                self.add_error("confirm_password", "Xác nhận mật khẩu không khớp.")
            candidate = User(
                username=cleaned_data.get("username") or "",
                email=cleaned_data.get("email") or "",
                phone_number=cleaned_data.get("phone_number") or "",
            )
            candidate.normalized_phone = normalize_phone(candidate.phone_number) if candidate.phone_number else ""
            errors = password_policy_errors(password, candidate)
            if errors:
                self.add_error("password", errors[0])
        if (
            self.instance.pk
            and not cleaned_data.get("is_active", False)
            and self.instance.owned_branches.filter(is_active=True).exists()
        ):
            self.add_error("is_active", "Hãy chuyển chủ các chi nhánh đang hoạt động trước khi khóa tài khoản.")
        if cleaned_data.get("assign_branches") and not cleaned_data.get("is_active", False):
            self.add_error(
                "assign_branches",
                "Chỉ có thể giao chi nhánh cho tài khoản được phép đăng nhập.",
            )
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.BRANCH_OWNER
        user.is_staff = False
        user.is_superuser = False
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class BranchStaffForm(forms.Form):
    branch = forms.ModelChoiceField(
        label="Chi nhánh",
        queryset=Branch.objects.none(),
        empty_label="Chọn chi nhánh",
    )
    role_key = forms.ChoiceField(label="Vai trò")
    full_name = forms.CharField(
        label="Họ và tên",
        min_length=2,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "Ví dụ: Nguyễn Văn An"}),
    )
    email = forms.EmailField(
        label="Thư điện tử",
        max_length=254,
        widget=forms.EmailInput(attrs={"placeholder": "nhanvien@example.com"}),
    )
    phone_number = forms.CharField(
        label="Số điện thoại",
        max_length=20,
        widget=forms.TextInput(attrs={"placeholder": "Ví dụ: 0901234567"}),
    )
    password = forms.CharField(
        label="Mật khẩu tạm thời",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Tối thiểu 8 ký tự, có chữ hoa, chữ thường, số và ký tự đặc biệt.",
    )
    confirm_password = forms.CharField(
        label="Xác nhận mật khẩu",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.actor = actor
        self.fields["branch"].queryset = _manageable_branches(actor)
        self.fields["role_key"].choices = [
            (key, definition["label"])
            for key, definition in ROLE_DEFINITIONS.items()
            if not definition["owner_only"] or actor.role == User.Role.BRANCH_OWNER
        ]

    def clean_full_name(self):
        return str(self.cleaned_data.get("full_name") or "").strip()

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email") or "")
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Thư điện tử đã được sử dụng bởi tài khoản khác.")
        return email

    def clean_phone_number(self):
        phone = normalize_phone(self.cleaned_data.get("phone_number") or "")
        if User.objects.filter(normalized_phone=phone).exists():
            raise forms.ValidationError("Số điện thoại đã được sử dụng bởi tài khoản khác.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        branch = cleaned_data.get("branch")
        role_key = cleaned_data.get("role_key")
        definition = ROLE_DEFINITIONS.get(role_key)
        if definition and definition["owner_only"] and branch:
            if not _can_create_manager(self.actor, branch):
                self.add_error(
                    "role_key",
                    "Chỉ Chủ chi nhánh được tạo tài khoản Quản lý.",
                )
        password = cleaned_data.get("password") or ""
        if password != (cleaned_data.get("confirm_password") or ""):
            self.add_error("confirm_password", "Xác nhận mật khẩu không khớp.")
        if password:
            candidate = User(
                username=_unique_staff_username(),
                first_name=cleaned_data.get("full_name") or "",
                email=cleaned_data.get("email") or "",
                phone_number=cleaned_data.get("phone_number") or "",
                normalized_phone=cleaned_data.get("phone_number") or "",
            )
            errors = password_policy_errors(password, candidate)
            if errors:
                self.add_error("password", errors[0])
        return cleaned_data

    @transaction.atomic
    def save(self):
        definition = ROLE_DEFINITIONS[self.cleaned_data["role_key"]]
        user = User(
            username=_unique_staff_username(),
            first_name=self.cleaned_data["full_name"],
            email=self.cleaned_data["email"],
            phone_number=self.cleaned_data["phone_number"],
            normalized_phone=self.cleaned_data["phone_number"],
            role=definition["user_role"],
            is_active=True,
            is_staff=False,
            is_superuser=False,
            password_changed_at=timezone.now(),
        )
        user.set_password(self.cleaned_data["password"])
        user.save()
        membership = BranchMembership.objects.create(
            user=user,
            branch=self.cleaned_data["branch"],
            membership_role=definition["membership_role"],
            can_manage_team=definition["can_manage_team"],
            is_active=True,
        )
        return user, membership
