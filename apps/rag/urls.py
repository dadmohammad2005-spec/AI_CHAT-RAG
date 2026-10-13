from django.urls import path
from apps.rag.views import RAGQueryAPIView, QueryHistoryListView

app_name = "rag"

urlpatterns = [
    path("query/", RAGQueryAPIView.as_view(), name="chat-query"),
    path("history/", QueryHistoryListView.as_view(), name="chat-history"),
]
