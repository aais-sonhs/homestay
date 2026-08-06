"""Reusable list-view and pagination helpers.

This keeps filter state and query-string pagination consistent across backoffice
applications, following the same convention as Fasthub.
"""

from collections.abc import Mapping
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models.query import QuerySet, ValuesIterable
from django.views.generic import ListView


class ContextRow(dict):
    """Expose ``values()`` rows with model-like attribute access."""

    decimal_quantizer = Decimal("0.01")

    @staticmethod
    def _alias_key(key):
        if key == "id":
            return "pk"
        if key == "pk":
            return "id"
        return key

    @classmethod
    def _normalize_value(cls, value):
        if isinstance(value, Decimal):
            return value.quantize(cls.decimal_quantizer)
        return value

    def __getattr__(self, name):
        if super().__contains__(name):
            return self._normalize_value(super().__getitem__(name))
        alias = self._alias_key(name)
        if super().__contains__(alias):
            return self._normalize_value(super().__getitem__(alias))
        raise AttributeError(f"{self.__class__.__name__} has no attribute {name!r}")

    def __getitem__(self, key):
        if super().__contains__(key):
            return self._normalize_value(super().__getitem__(key))
        return self._normalize_value(super().__getitem__(self._alias_key(key)))

    def get(self, key, default=None):
        if super().__contains__(key):
            return self._normalize_value(super().get(key, default))
        return self._normalize_value(super().get(self._alias_key(key), default))


def adapt_mapping_rows(rows):
    if isinstance(rows, QuerySet):
        iterable_class = getattr(rows, "_iterable_class", None)
        if iterable_class and issubclass(iterable_class, ValuesIterable):
            return [ContextRow(row) for row in rows]
        return rows
    if isinstance(rows, list) and rows and isinstance(rows[0], Mapping):
        return [row if isinstance(row, ContextRow) else ContextRow(row) for row in rows]
    if isinstance(rows, tuple) and rows and isinstance(rows[0], Mapping):
        return tuple(row if isinstance(row, ContextRow) else ContextRow(row) for row in rows)
    return rows


def build_pagination_query(request, page_parameter="page"):
    params = request.GET.copy()
    params.pop(page_parameter, None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


def paginate_context(request, rows, *, context_object_name, per_page=20, page_parameter="page"):
    paginator = Paginator(rows, per_page)
    page_obj = paginator.get_page(request.GET.get(page_parameter))
    page_obj.object_list = adapt_mapping_rows(page_obj.object_list)
    return {
        context_object_name: page_obj.object_list,
        "paginator": paginator,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "pagination_query": build_pagination_query(request, page_parameter),
    }


class FilteredListView(ListView):
    filter_fields = ()

    def build_filter_state(self):
        return {name: self.request.GET.get(name, "").strip() for name in self.filter_fields}

    def get_filter_state(self):
        if not hasattr(self, "_filter_state"):
            self._filter_state = self.build_filter_state()
        return self._filter_state

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        object_list = context.get("object_list")
        adapted = adapt_mapping_rows(object_list)
        context_name = self.context_object_name or self.get_context_object_name(
            getattr(self, "object_list", None)
        )
        if adapted is not object_list:
            context["object_list"] = adapted
            if context_name:
                context[context_name] = adapted
            if context.get("page_obj") is not None:
                context["page_obj"].object_list = adapted
        context["filters"] = self.get_filter_state()
        context["pagination_query"] = build_pagination_query(self.request)
        return context

