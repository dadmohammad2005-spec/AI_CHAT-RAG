import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TenantAwareModel


class QueryLog(TenantAwareModel):
    """
    Audit log of all queries executed against the RAG engine within a tenant.
    Captures question, synthesized answer, retrieved source citations, and token consumption.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="query_logs",
    )
    question = models.TextField(help_text="User's natural language question")
    answer = models.TextField(help_text="Generated grounded answer from LLM")
    retrieved_sources = models.JSONField(
        default=list,
        help_text="List of source citations with document name, page number, snippet, and similarity score",
    )
    tokens_used = models.IntegerField(default=0, help_text="Total tokens consumed (prompt + completion)")
    latency_ms = models.FloatField(default=0.0, help_text="Round-trip query latency in milliseconds")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "user"]),
        ]
        verbose_name = "Query Log"
        verbose_name_plural = "Query Logs"

    def __str__(self):
        return f"Query ({self.tenant.name}): {self.question[:40]}... [{self.tokens_used} tokens]"
