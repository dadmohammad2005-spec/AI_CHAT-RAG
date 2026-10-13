from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    # REST API v1
    path("api/v1/documents/", include("apps.documents.urls")),
    path("api/v1/chat/", include("apps.rag.urls")),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    # Frontend Web UI (Tailwind + Alpine + HTMX)
    path("", include("apps.web.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
