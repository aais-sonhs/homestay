from django import forms

from .models import User


MAX_AVATAR_SIZE = 5 * 1024 * 1024
ALLOWED_AVATAR_FORMATS = {"GIF", "JPEG", "PNG", "WEBP"}


class ForgotPasswordRequestForm(forms.Form):
    identifier = forms.CharField(label="Thư điện tử hoặc số điện thoại", max_length=254)
    channel = forms.ChoiceField(
        label="Nhận mã qua",
        choices=(("email", "Thư điện tử"), ("sms", "Tin nhắn SMS")),
    )


class VerifyOTPForm(forms.Form):
    otp = forms.CharField(
        label="Mã xác thực",
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )


class ResetPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="Mật khẩu mới",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Xác nhận mật khẩu mới",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


class AuthenticatedPasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Mật khẩu hiện tại",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    new_password = forms.CharField(
        label="Mật khẩu mới",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    confirm_password = forms.CharField(
        label="Xác nhận mật khẩu mới",
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )


class AvatarUpdateForm(forms.ModelForm):
    remove_avatar = forms.BooleanField(
        required=False,
        label="Xóa ảnh đại diện hiện tại",
    )

    class Meta:
        model = User
        fields = ("avatar",)
        labels = {"avatar": "Ảnh đại diện mới"}
        help_texts = {
            "avatar": "Chấp nhận JPG, PNG, GIF hoặc WEBP; dung lượng tối đa 5 MB.",
        }
        widgets = {
            "avatar": forms.FileInput(
                attrs={
                    "accept": ".jpg,.jpeg,.png,.gif,.webp,image/jpeg,image/png,image/gif,image/webp",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["avatar"].required = False
        self._previous_avatar_name = self.instance.avatar.name if self.instance.avatar else ""
        self._avatar_storage = self.instance.avatar.storage

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        uploaded_avatar = self.files.get(self.add_prefix("avatar"))
        if not uploaded_avatar:
            return avatar
        if uploaded_avatar.size > MAX_AVATAR_SIZE:
            raise forms.ValidationError("Ảnh đại diện không được vượt quá 5 MB.")
        image_format = getattr(getattr(avatar, "image", None), "format", "").upper()
        if image_format not in ALLOWED_AVATAR_FORMATS:
            raise forms.ValidationError("Chỉ chấp nhận ảnh JPG, PNG, GIF hoặc WEBP.")
        return avatar

    def clean(self):
        cleaned_data = super().clean()
        has_upload = bool(self.files.get(self.add_prefix("avatar")))
        remove_avatar = cleaned_data.get("remove_avatar", False)
        if has_upload and remove_avatar:
            raise forms.ValidationError("Chỉ chọn một thao tác: tải ảnh mới hoặc xóa ảnh hiện tại.")
        if not has_upload and not remove_avatar:
            raise forms.ValidationError("Vui lòng chọn ảnh đại diện mới hoặc chọn xóa ảnh hiện tại.")
        if remove_avatar and not self._previous_avatar_name:
            raise forms.ValidationError("Tài khoản chưa có ảnh đại diện để xóa.")
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get("remove_avatar"):
            user.avatar = ""
        if commit:
            user.save(update_fields=["avatar"])
            current_avatar_name = user.avatar.name if user.avatar else ""
            if self._previous_avatar_name and self._previous_avatar_name != current_avatar_name:
                self._avatar_storage.delete(self._previous_avatar_name)
        return user
