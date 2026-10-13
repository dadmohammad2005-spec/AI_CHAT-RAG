from django.contrib import admin
from apps.rag.models import QueryLog


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = (
        "tenant",
        "user",
        "short_question",
        "tokens_used",
        "latency_ms",
        "created_at",
    )
    search_fields = ("question", "answer", "tenant__name")
    list_filter = ("tenant", "created_at")
    readonly_fields = (
        "id",
        "tenant",
        "user",
        "question",
        "answer",
        "retrieved_sources",
        "tokens_used",
        "latency_ms",
        "created_at",
    )

    def short_question(self, obj):
        return obj.question[:60] + "..." if len(obj.question) > 60 else obj.question
