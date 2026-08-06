from django import template

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
