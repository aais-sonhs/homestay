from django import template
from decimal import Decimal, InvalidOperation

from common.display import display_label, localized_json, localized_system_text


register = template.Library()


@register.filter
def vi_label(value):
    return display_label(value)


@register.filter
def vi_json(value):
    return localized_json(value)


@register.filter
def vi_text(value):
    return localized_system_text(value)


@register.filter
def money_vi(value):
    try:
        amount = Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return value
    decimal_places = 0 if amount == amount.to_integral_value() else 2
    formatted = f"{amount:,.{decimal_places}f}"
    return formatted.replace(",", "_").replace(".", ",").replace("_", ".")
