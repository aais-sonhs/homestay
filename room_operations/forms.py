from datetime import timedelta

from django import forms
from django.utils import timezone

from common.forms import DateTimeLocalInput, StyledModelForm
from organizations.models import Branch, Room

from .models import RoomAsset, RoomBlocker, RoomStopSell
from .selectors import room_sales_management_branch_queryset


class BranchAwareSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            branch_id = getattr(instance, "branch_id", None)
            room_id = getattr(instance, "room_id", None)
            if branch_id:
                option["attrs"]["data-branch-id"] = str(branch_id)
            if room_id:
                option["attrs"]["data-room-id"] = str(room_id)
        return option


class StopSellRoomField(forms.ModelChoiceField):
    def label_from_instance(self, room):
        return f"{room.branch.name} — {room.code} · {room.name}"


class StopSellBlockerField(forms.ModelChoiceField):
    def label_from_instance(self, blocker):
        return f"{blocker.room.code} · {blocker.get_kind_display()}: {blocker.reason}"


class RoomStopSellCreateForm(forms.Form):
    branch = forms.ModelChoiceField(label="Chi nhánh", queryset=Branch.objects.none())
    room = StopSellRoomField(
        label="Phòng",
        queryset=Room.objects.none(),
        widget=BranchAwareSelect,
    )
    blocker = StopSellBlockerField(
        label="Blocker nguồn (nếu đã có)",
        queryset=RoomBlocker.objects.none(),
        required=False,
        widget=BranchAwareSelect,
        help_text="Để trống nếu đây là quyết định dừng bán thủ công; hệ thống sẽ tạo blocker mới.",
    )
    reason_code = forms.ChoiceField(label="Nhóm lý do", choices=RoomStopSell.ReasonCode.choices)
    reason = forms.CharField(
        label="Lý do cụ thể",
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Mô tả lý do và ảnh hưởng tới khả năng bán"}),
    )
    starts_at = forms.DateTimeField(
        label="Bắt đầu dừng bán",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=DateTimeLocalInput(),
    )
    planned_end_at = forms.DateTimeField(
        label="Dự kiến kết thúc",
        input_formats=["%Y-%m-%dT%H:%M"],
        widget=DateTimeLocalInput(),
        help_text="Phòng vẫn bị chặn sau mốc này cho đến khi có người xác nhận mở lại.",
    )

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        branches = room_sales_management_branch_queryset(user)
        self.fields["branch"].queryset = branches
        self.fields["branch"].empty_label = "Chọn chi nhánh"
        self.fields["room"].queryset = (
            Room.objects.filter(branch__in=branches)
            .select_related("branch")
            .order_by("branch__name", "code")
        )
        self.fields["room"].empty_label = "Chọn phòng"
        self.fields["blocker"].queryset = (
            RoomBlocker.objects.filter(
                branch__in=branches,
                status=RoomBlocker.Status.ACTIVE,
            )
            .select_related("branch", "room")
            .order_by("branch__name", "room__code", "-starts_at")
        )
        self.fields["blocker"].empty_label = "Tạo blocker thủ công mới"
        if not self.is_bound:
            now = timezone.localtime().replace(second=0, microsecond=0)
            self.initial.setdefault("starts_at", now)
            self.initial.setdefault("planned_end_at", now + timedelta(days=1))

    def clean_reason(self):
        return str(self.cleaned_data.get("reason") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        branch = cleaned_data.get("branch")
        room = cleaned_data.get("room")
        blocker = cleaned_data.get("blocker")
        starts_at = cleaned_data.get("starts_at")
        planned_end_at = cleaned_data.get("planned_end_at")
        if branch and room and room.branch_id != branch.id:
            self.add_error("room", "Phòng không thuộc chi nhánh đã chọn.")
        if blocker and room and blocker.room_id != room.id:
            self.add_error("blocker", "Blocker nguồn không thuộc phòng đã chọn.")
        if blocker and branch and blocker.branch_id != branch.id:
            self.add_error("blocker", "Blocker nguồn không thuộc chi nhánh đã chọn.")
        if starts_at and starts_at < timezone.now() - timedelta(minutes=5):
            self.add_error("starts_at", "Không thể tạo khoảng dừng bán trong quá khứ.")
        if starts_at and planned_end_at and planned_end_at <= starts_at:
            self.add_error("planned_end_at", "Thời gian kết thúc phải sau thời gian bắt đầu.")
        return cleaned_data


class RoomOperationsActionForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    note = forms.CharField(
        label="Ghi chú bắt buộc",
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Nêu kết quả xử lý hoặc lý do thao tác"}),
    )

    def clean_note(self):
        return str(self.cleaned_data.get("note") or "").strip()


class RoomAssetForm(StyledModelForm):
    class Meta:
        model = RoomAsset
        fields = (
            "branch",
            "room",
            "code",
            "name",
            "category",
            "status",
            "serial_number",
            "purchase_date",
            "last_maintenance_at",
            "next_maintenance_at",
            "note",
            "is_active",
        )
        labels = {
            "branch": "Chi nhánh",
            "room": "Phòng / căn",
            "code": "Mã tài sản",
            "name": "Tên thiết bị / tài sản",
            "category": "Nhóm tài sản",
            "status": "Trạng thái",
            "serial_number": "Số serial",
            "purchase_date": "Ngày mua",
            "last_maintenance_at": "Bảo trì gần nhất",
            "next_maintenance_at": "Hạn bảo trì tiếp theo",
            "note": "Ghi chú",
            "is_active": "Đang theo dõi",
        }
        widgets = {
            "purchase_date": forms.DateInput(attrs={"type": "date"}),
            "last_maintenance_at": forms.DateInput(attrs={"type": "date"}),
            "next_maintenance_at": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        branches = room_sales_management_branch_queryset(user)
        self.fields["branch"].queryset = branches
        self.fields["branch"].empty_label = "Chọn chi nhánh"
        self.fields["room"].queryset = (
            Room.objects.filter(branch__in=branches)
            .select_related("branch")
            .order_by("branch__name", "code")
        )
        self.fields["room"].empty_label = "Tài sản dùng chung chi nhánh"

    def clean_code(self):
        return str(self.cleaned_data.get("code") or "").strip().upper()

    def clean(self):
        cleaned_data = super().clean()
        branch = cleaned_data.get("branch")
        room = cleaned_data.get("room")
        if branch and room and room.branch_id != branch.id:
            self.add_error("room", "Phòng không thuộc chi nhánh đã chọn.")
        return cleaned_data
