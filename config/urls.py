from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from accounts.views import dashboard


def serve_media(request, path):
    """Serve uploaded media from the active MEDIA_ROOT even when settings are overridden."""
    return serve(request, path, document_root=settings.MEDIA_ROOT)


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("", include("analytics.urls")),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("housekeeping.urls")),
    path("", include("organizations.urls")),
    path("", include("reservations.urls")),
    path("", include("room_operations.urls")),
    # Fasthub cũng phục vụ MEDIA_ROOT qua route này. Homestay chạy DEBUG=False,
    # nên không thể dựa vào django.conf.urls.static.static() để hiển thị avatar.
    re_path(r"^media/(?P<path>.*)$", serve_media),
]
