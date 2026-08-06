from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from accounts.views import dashboard

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("housekeeping.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
