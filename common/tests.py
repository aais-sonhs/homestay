from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from .list_views import paginate_collection, paginate_context


class PaginationHelperTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_standard_pagination_keeps_filters_and_returns_requested_page(self):
        request = self.factory.get("/items/", {"page": "2", "q": "phòng 101"})

        context = paginate_context(
            request,
            list(range(45)),
            context_object_name="rows",
            per_page=20,
        )

        self.assertEqual(context["rows"], list(range(20, 40)))
        self.assertEqual(context["paginator"].count, 45)
        self.assertEqual(context["page_obj"].number, 2)
        self.assertEqual(context["pagination_query"], "&q=ph%C3%B2ng+101")

    def test_independent_pagination_only_replaces_its_own_page_parameter(self):
        request = self.factory.get(
            "/queues/",
            {
                "supply_page": "2",
                "issue_page": "3",
                "status": "PENDING",
            },
        )

        pagination = paginate_collection(
            request,
            list(range(45)),
            per_page=20,
            page_parameter="supply_page",
        )

        self.assertEqual(pagination["items"], list(range(20, 40)))
        self.assertEqual(pagination["page_parameter"], "supply_page")
        self.assertNotIn("supply_page", pagination["pagination_query"])
        self.assertIn("issue_page=3", pagination["pagination_query"])
        self.assertIn("status=PENDING", pagination["pagination_query"])

        html = render_to_string("shared/pagination.html", pagination)
        self.assertIn("?supply_page=1", html)
        self.assertIn("?supply_page=3", html)
        self.assertIn("issue_page=3", html)
