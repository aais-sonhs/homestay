from datetime import timedelta
from decimal import Decimal

from django import forms
from django.db.models import Q
from django.utils import timezone

from common.forms import DateTimeLocalInput, StyledModelForm, VietnameseMoneyField
from housekeeping.models import (
    Booking,
    BookingSpecialRequest,
    CapitalEntry,
    OperatingExpense,
)
from organizations.models import Room
from room_operations.selectors import find_room_stop_sell_conflict

from .selectors import booking_creation_branch_queryset
from .selectors import revenue_branch_queryset


MONEY_ZERO = Decimal("0.00")


def _booking_money_field(label, help_text):
    return VietnameseMoneyField(
        label=label,
        help_text=help_text,
        required=False,
        min_value=MONEY_ZERO,
        max_digits=14,
        decimal_places=2,
    )


def _clean_booking_financials(form, cleaned_data):
    for field_name in (
        "room_charge",
        "service_charge",
        "discount_amount",
        "paid_amount",
    ):
        cleaned_data[field_name] = cleaned_data.get(field_name) or MONEY_ZERO
    gross_amount = cleaned_data["room_charge"] + cleaned_data["service_charge"]
    if cleaned_data["discount_amount"] > gross_amount:
        form.add_error(
            "discount_amount",
            "Tiền giảm giá không được lớn hơn tiền phòng và phụ thu.",
        )
    total_amount = gross_amount - cleaned_data["discount_amount"]
    if cleaned_data["paid_amount"] > total_amount:
        form.add_error(
            "paid_amount",
            "Số tiền đã thu không được lớn hơn tổng giá trị booking.",
        )


class BranchRoomSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        instance = getattr(value, "instance", None)
        if instance is not None:
            option["attrs"]["data-branch-id"] = str(instance.branch_id)
        return option


class BookingRoomField(forms.ModelChoiceField):
    def label_from_instance(self, room):
        room_type = f" · {room.room_type}" if room.room_type else ""
        return f"{room.branch.name} — {room.code} · {room.name}{room_type}"


class BookingSpecialRequestForm(forms.Form):
    request_type = forms.ChoiceField(
        label="Loại yêu cầu",
        choices=BookingSpecialRequest.RequestType.choices,
    )
    applies_to = forms.ChoiceField(
        label="Thời điểm áp dụng",
        choices=BookingSpecialRequest.AppliesTo.choices,
        initial=BookingSpecialRequest.AppliesTo.CHECKIN,
    )
    priority = forms.ChoiceField(
        label="Mức ưu tiên",
        choices=BookingSpecialRequest.Priority.choices,
        initial=BookingSpecialRequest.Priority.NORMAL,
    )
    description = forms.CharField(
        label="Nội dung yêu cầu",
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Ví dụ: Chuẩn bị thêm gối không lông vũ"}),
    )
    quantity = forms.IntegerField(
        label="Số lượng",
        min_value=1,
        max_value=99,
        required=False,
        widget=forms.NumberInput(attrs={"min": 1, "max": 99, "placeholder": "—"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        has_metadata = any(
            self.data.get(self.add_prefix(field))
            for field in ("quantity",)
        )
        if has_metadata and not str(cleaned_data.get("description") or "").strip():
            self.add_error("description", "Vui lòng nhập nội dung cho yêu cầu này.")
        return cleaned_data


BookingSpecialRequestFormSet = forms.formset_factory(
    BookingSpecialRequestForm,
    extra=1,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


def special_request_formset_initial(booking):
    items = list(booking.special_request_items.all())
    if items:
        return [
            {
                "request_type": item.request_type,
                "applies_to": item.applies_to,
                "priority": item.priority,
                "description": item.description,
                "quantity": item.quantity,
            }
            for item in items
        ]
    if booking.special_requests:
        return [
            {
                "request_type": BookingSpecialRequest.RequestType.OTHER,
                "applies_to": BookingSpecialRequest.AppliesTo.ALL,
                "priority": BookingSpecialRequest.Priority.NORMAL,
                "description": booking.special_requests,
            }
        ]
    return []


class BookingCreateForm(StyledModelForm):
    room = BookingRoomField(
        label="Phòng",
        queryset=Room.objects.none(),
        widget=BranchRoomSelect,
    )
    room_charge = _booking_money_field(
        "Tiền phòng",
        "Nhập tổng tiền phòng của cả kỳ lưu trú.",
    )
    service_charge = _booking_money_field(
        "Phụ thu / dịch vụ",
        "Ví dụ: phụ thu thêm người, nước uống hoặc dịch vụ tính phí.",
    )
    discount_amount = _booking_money_field(
        "Giảm giá",
        "Để trống nếu booking không có giảm giá.",
    )
    paid_amount = _booking_money_field(
        "Đã thu",
        "Tổng tiền cọc và thanh toán đã nhận từ khách.",
    )

    class Meta:
        model = Booking
        fields = (
            "branch",
            "room",
            "code",
            "guest_name",
            "guest_phone",
            "guest_count",
            "checkin_at",
            "checkout_at",
            "room_charge",
            "service_charge",
            "discount_amount",
            "paid_amount",
        )
        labels = {
            "branch": "Chi nhánh",
            "code": "Mã booking",
            "guest_name": "Tên khách",
            "guest_phone": "Số điện thoại khách",
            "guest_count": "Số khách",
            "checkin_at": "Thời gian nhận phòng",
            "checkout_at": "Thời gian trả phòng",
        }
        help_texts = {
            "code": "Có thể để trống để hệ thống tự sinh mã.",
            "checkin_at": "Lịch chuẩn bị phòng được tạo trước giờ nhận phòng 90 phút.",
            "checkout_at": "Lịch dọn phòng được tạo ngay từ giờ khách trả phòng.",
        }
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "Để trống để tự sinh"}),
            "guest_name": forms.TextInput(attrs={"placeholder": "Họ và tên khách"}),
            "guest_phone": forms.TextInput(attrs={"placeholder": "Ví dụ: 0901234567"}),
            "guest_count": forms.NumberInput(attrs={"min": 1, "max": 99}),
            "checkin_at": DateTimeLocalInput(),
            "checkout_at": DateTimeLocalInput(),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        branches = booking_creation_branch_queryset(user)
        self.fields["branch"].queryset = branches
        self.fields["branch"].empty_label = "Chọn chi nhánh"
        self.fields["room"].queryset = (
            Room.objects.filter(branch__in=branches)
            .select_related("branch")
            .order_by("branch__name", "code")
        )
        self.fields["room"].empty_label = "Chọn phòng"
        self.fields["code"].required = False
        self.fields["guest_name"].required = True
        self.fields["guest_phone"].required = True
        self.fields["checkin_at"].required = True
        self.fields["checkout_at"].required = True
        self.fields["checkin_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["checkout_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        if not self.is_bound:
            local_now = timezone.localtime().replace(second=0, microsecond=0)
            checkin = (local_now + timedelta(days=1)).replace(hour=14, minute=0)
            self.initial.setdefault("checkin_at", checkin)
            self.initial.setdefault("checkout_at", checkin + timedelta(days=1) - timedelta(hours=2))

    def clean_code(self):
        return str(self.cleaned_data.get("code") or "").strip().upper()

    def clean_guest_name(self):
        return str(self.cleaned_data.get("guest_name") or "").strip()

    def clean_guest_phone(self):
        return str(self.cleaned_data.get("guest_phone") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        branch = cleaned_data.get("branch")
        room = cleaned_data.get("room")
        checkin_at = cleaned_data.get("checkin_at")
        checkout_at = cleaned_data.get("checkout_at")
        code = cleaned_data.get("code")

        if branch and room and room.branch_id != branch.id:
            self.add_error("room", "Phòng không thuộc chi nhánh đã chọn.")
        if room and (room.is_locked or room.status == Room.Status.OUT_OF_SERVICE):
            self.add_error("room", "Phòng đang bị khóa hoặc ngừng phục vụ, không thể nhận booking.")
        if checkin_at and checkin_at < timezone.now() - timedelta(minutes=5):
            self.add_error("checkin_at", "Thời gian nhận phòng không được ở trong quá khứ.")
        if checkin_at and checkout_at and checkout_at <= checkin_at:
            self.add_error("checkout_at", "Thời gian trả phòng phải sau thời gian nhận phòng.")
        if branch and code and Booking.objects.filter(branch=branch, code__iexact=code).exists():
            self.add_error("code", "Mã booking đã tồn tại tại chi nhánh này.")
        if room and checkin_at and checkout_at:
            if find_room_stop_sell_conflict(room, checkin_at, checkout_at):
                self.add_error("room", "Phòng đang dừng bán trong khoảng thời gian này.")
            overlapping = (
                Booking.objects.filter(
                    room=room,
                    checkin_at__lt=checkout_at,
                    checkout_at__gt=checkin_at,
                )
                .exclude(status=Booking.Status.CANCELLED)
                .exists()
            )
            if overlapping:
                self.add_error("room", "Phòng đã có booking trùng khoảng thời gian này.")
        _clean_booking_financials(self, cleaned_data)
        return cleaned_data


class BookingUpdateForm(StyledModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput)
    room = BookingRoomField(
        label="Phòng",
        queryset=Room.objects.none(),
    )
    room_charge = _booking_money_field(
        "Tiền phòng",
        "Nhập tổng tiền phòng của cả kỳ lưu trú.",
    )
    service_charge = _booking_money_field(
        "Phụ thu / dịch vụ",
        "Ví dụ: phụ thu thêm người, nước uống hoặc dịch vụ tính phí.",
    )
    discount_amount = _booking_money_field(
        "Giảm giá",
        "Để trống nếu booking không có giảm giá.",
    )
    paid_amount = _booking_money_field(
        "Đã thu",
        "Tổng tiền cọc và thanh toán đã nhận từ khách.",
    )

    class Meta:
        model = Booking
        fields = (
            "version",
            "room",
            "guest_name",
            "guest_phone",
            "guest_count",
            "checkin_at",
            "checkout_at",
            "room_charge",
            "service_charge",
            "discount_amount",
            "paid_amount",
        )
        labels = BookingCreateForm.Meta.labels
        help_texts = {
            "checkin_at": "Đổi mốc này sẽ cập nhật lịch chuẩn bị phòng liên quan.",
            "checkout_at": "Đổi mốc này sẽ cập nhật lịch dọn sau trả phòng liên quan.",
        }
        widgets = BookingCreateForm.Meta.widgets

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        branch = self.instance.branch
        self.fields["room"].queryset = (
            Room.objects.filter(branch=branch)
            .select_related("branch")
            .order_by("code")
        )
        self.fields["guest_name"].required = True
        self.fields["guest_phone"].required = True
        self.fields["checkin_at"].required = True
        self.fields["checkout_at"].required = True
        self.fields["checkin_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["checkout_at"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.initial.setdefault("version", self.instance.version)

    def clean_guest_name(self):
        return str(self.cleaned_data.get("guest_name") or "").strip()

    def clean_guest_phone(self):
        return str(self.cleaned_data.get("guest_phone") or "").strip()

    def clean(self):
        cleaned_data = super().clean()
        room = cleaned_data.get("room")
        checkin_at = cleaned_data.get("checkin_at")
        checkout_at = cleaned_data.get("checkout_at")
        if room and room.branch_id != self.instance.branch_id:
            self.add_error("room", "Phòng không thuộc chi nhánh của booking.")
        if room and (room.is_locked or room.status == Room.Status.OUT_OF_SERVICE):
            self.add_error("room", "Phòng đang bị khóa hoặc ngừng phục vụ, không thể nhận booking.")
        if checkin_at and checkin_at < timezone.now() - timedelta(minutes=5):
            self.add_error("checkin_at", "Thời gian nhận phòng không được ở trong quá khứ.")
        if checkin_at and checkout_at and checkout_at <= checkin_at:
            self.add_error("checkout_at", "Thời gian trả phòng phải sau thời gian nhận phòng.")
        if room and checkin_at and checkout_at:
            schedule_changed = bool(
                room.id != self.instance.room_id
                or checkin_at != self.instance.checkin_at
                or checkout_at != self.instance.checkout_at
            )
            if schedule_changed and find_room_stop_sell_conflict(room, checkin_at, checkout_at):
                self.add_error("room", "Phòng đang dừng bán trong khoảng thời gian này.")
            overlapping = (
                Booking.objects.filter(
                    room=room,
                    checkin_at__lt=checkout_at,
                    checkout_at__gt=checkin_at,
                )
                .exclude(pk=self.instance.pk)
                .exclude(status=Booking.Status.CANCELLED)
                .exists()
            )
            if overlapping:
                self.add_error("room", "Phòng đã có booking trùng khoảng thời gian này.")
        _clean_booking_financials(self, cleaned_data)
        return cleaned_data


class BookingFinancialUpdateForm(StyledModelForm):
    version = forms.IntegerField(widget=forms.HiddenInput)
    room_charge = _booking_money_field(
        "Tiền phòng",
        "Tổng tiền phòng của cả kỳ lưu trú.",
    )
    service_charge = _booking_money_field(
        "Phụ thu / dịch vụ",
        "Các khoản dịch vụ và phụ thu tính thêm.",
    )
    discount_amount = _booking_money_field(
        "Giảm giá",
        "Tổng số tiền giảm cho booking.",
    )
    paid_amount = _booking_money_field(
        "Đã thu",
        "Cập nhật tổng tiền cọc và thanh toán thực tế đã nhận.",
    )

    class Meta:
        model = Booking
        fields = (
            "version",
            "room_charge",
            "service_charge",
            "discount_amount",
            "paid_amount",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial.setdefault("version", self.instance.version)

    def clean(self):
        cleaned_data = super().clean()
        _clean_booking_financials(self, cleaned_data)
        return cleaned_data


class BookingCancelForm(forms.Form):
    version = forms.IntegerField(widget=forms.HiddenInput)
    reason = forms.CharField(
        label="Lý do hủy booking",
        max_length=500,
        widget=forms.TextInput(attrs={"placeholder": "Nhập lý do bắt buộc"}),
    )


class CapitalEntryForm(StyledModelForm):
    amount = _booking_money_field("Số tiền", "Số vốn thực tế đã ghi nhận.")

    class Meta:
        model = CapitalEntry
        fields = ("branch", "title", "amount", "capital_date", "source", "notes")
        labels = {
            "branch": "Chi nhánh",
            "title": "Tên nguồn vốn",
            "capital_date": "Ngày ghi nhận",
            "source": "Nguồn vốn",
            "notes": "Ghi chú",
        }
        widgets = {
            "capital_date": forms.DateInput(attrs={"type": "date"}),
            "title": forms.TextInput(attrs={"placeholder": "Ví dụ: Vốn đầu tư ban đầu"}),
            "source": forms.TextInput(attrs={"placeholder": "Ví dụ: Chủ chi nhánh"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = revenue_branch_queryset(user)
        self.fields["branch"].empty_label = "Chọn chi nhánh"


class OperatingExpenseForm(StyledModelForm):
    amount = _booking_money_field("Số tiền", "Số tiền dự kiến hoặc đã chi.")

    class Meta:
        model = OperatingExpense
        fields = (
            "branch",
            "name",
            "category",
            "amount",
            "expense_date",
            "payment_status",
            "notes",
        )
        labels = {
            "branch": "Chi nhánh",
            "name": "Khoản chi",
            "category": "Nhóm chi phí",
            "expense_date": "Ngày phát sinh",
            "payment_status": "Trạng thái chi",
            "notes": "Ghi chú",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ví dụ: Tiền điện tháng này"}),
            "category": forms.TextInput(attrs={"placeholder": "Ví dụ: Điện nước, vật tư, sửa chữa"}),
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["branch"].queryset = revenue_branch_queryset(user)
        self.fields["branch"].empty_label = "Chọn chi nhánh"
