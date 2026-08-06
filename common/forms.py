"""Form fields and widgets shared by Django applications."""

import re
from decimal import Decimal, InvalidOperation

from django import forms


_VI_GROUPED_MONEY_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?$")
_EN_GROUPED_MONEY_RE = re.compile(r"^-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?$")


def normalize_vietnamese_money(value):
    if not isinstance(value, str):
        return value
    normalized = re.sub(r"\s*(?:vnd|[đ₫])\s*$", "", value.strip(), flags=re.IGNORECASE)
    normalized = normalized.replace("\xa0", "").replace(" ", "")
    if _VI_GROUPED_MONEY_RE.fullmatch(normalized):
        integer_part, separator, decimal_part = normalized.partition(",")
        normalized = integer_part.replace(".", "")
        return f"{normalized}.{decimal_part}" if separator else normalized
    if _EN_GROUPED_MONEY_RE.fullmatch(normalized):
        return normalized.replace(",", "")
    if "," in normalized and "." not in normalized:
        integer_part, separator, decimal_part = normalized.partition(",")
        if separator and decimal_part.isdigit() and len(decimal_part) <= 2:
            return f"{integer_part}.{decimal_part}"
    return normalized


class VietnameseMoneyInput(forms.TextInput):
    def __init__(self, attrs=None):
        defaults = {
            "autocomplete": "off",
            "data-money-input": "",
            "inputmode": "numeric",
            "placeholder": "0",
        }
        defaults.update(attrs or {})
        super().__init__(attrs=defaults)

    def format_value(self, value):
        if value in (None, ""):
            return ""
        try:
            amount = Decimal(str(normalize_vietnamese_money(value)))
        except (InvalidOperation, TypeError, ValueError):
            return super().format_value(value)
        decimal_value = format(amount, "f")
        sign = "-" if decimal_value.startswith("-") else ""
        decimal_value = decimal_value.removeprefix("-")
        integer_part, separator, decimal_part = decimal_value.partition(".")
        grouped = f"{int(integer_part or '0'):,}".replace(",", ".")
        if separator and decimal_part and any(digit != "0" for digit in decimal_part):
            return f"{sign}{grouped},{decimal_part}"
        return f"{sign}{grouped}"


class VietnameseMoneyField(forms.DecimalField):
    widget = VietnameseMoneyInput

    def to_python(self, value):
        return super().to_python(normalize_vietnamese_money(value))


class DateTimeLocalInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("format", "%Y-%m-%dT%H:%M")
        super().__init__(*args, **kwargs)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "checkbox-input"
            else:
                css_class = widget.attrs.get("class", "")
                widget.attrs["class"] = f"{css_class} form-input".strip()

