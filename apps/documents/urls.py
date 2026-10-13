from django.urls import path
from apps.documents.views import (
    DocumentListCreateView,
    DocumentUploadView,
    DocumentDetailView,
    DocumentChunksListView,
    DocumentReprocessView,
)

app_name = "documents"

urlpatterns = [
    path("", DocumentListCreateView.as_view(), name="document-list"),
    path("upload/", DocumentUploadView.as_view(), name="document-upload"),
    path("<uuid:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("<uuid:pk>/chunks/", DocumentChunksListView.as_view(), name="document-chunks"),
    path("<uuid:pk>/reprocess/", DocumentReprocessView.as_view(), name="document-reprocess"),
]
