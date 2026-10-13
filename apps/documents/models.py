import os
import uuid
from django.db import models
from django.conf import settings
from pgvector.django import VectorField, HnswIndex
from apps.core.models import TenantAwareModel


class SafeHnswIndex(HnswIndex):
    """
    HNSW Vector Index that generates native PostgreSQL pgvector index,
    and safely no-ops if running on SQLite during local developer testing.
    """

    def create_sql(self, model, schema_editor, using="", **kwargs):
        if schema_editor.connection.vendor != "postgresql":
            return "SELECT 1"
        return super().create_sql(model, schema_editor, using=using, **kwargs)

    def remove_sql(self, model, schema_editor, **kwargs):
        if schema_editor.connection.vendor != "postgresql":
            return "SELECT 1"
        return super().remove_sql(model, schema_editor, **kwargs)


def tenant_document_upload_path(instance, filename):
    """Store files organized by tenant id to guarantee storage segregation."""
    tenant_id = str(instance.tenant_id or "unassigned")
    clean_filename = os.path.basename(filename)
    return f"tenants/{tenant_id}/documents/{uuid.uuid4()}_{clean_filename}"


class Document(TenantAwareModel):
    """
    Uploaded enterprise document (PDF, DOCX, TXT) belonging to a tenant.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF Document"
        DOCX = "docx", "Word Document"
        TXT = "txt", "Plain Text"
        MD = "md", "Markdown"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_documents",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to=tenant_document_upload_path)
    file_type = models.CharField(max_length=16, choices=FileType.choices, default=FileType.PDF)
    file_size = models.BigIntegerField(default=0, help_text="File size in bytes")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING, db_index=True)
    error_message = models.TextField(blank=True, default="")
    total_chunks = models.IntegerField(default=0)
    total_pages = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "created_at"]),
        ]
        verbose_name = "Document"
        verbose_name_plural = "Documents"

    def __str__(self):
        return f"{self.title} ({self.status})"

    @property
    def file_size_display(self) -> str:
        """Human-readable file size."""
        size = self.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"


class DocumentChunk(TenantAwareModel):
    """
    Semantic text chunk extracted from a Document with vector embedding.
    Indexed for fast Cosine similarity search using pgvector.
    """

    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="chunks", db_index=True
    )
    content = models.TextField(help_text="Extracted text chunk content")
    page_number = models.IntegerField(default=1, help_text="1-based page number for exact citation")
    chunk_index = models.IntegerField(default=0, help_text="Sequence index within the document")
    token_count = models.IntegerField(default=0)
    embedding = VectorField(
        dimensions=getattr(settings, "AI_EMBEDDING_DIMENSION", 1536),
        null=True,
        blank=True,
        help_text="Dense vector representation (e.g., OpenAI text-embedding-3-small)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "chunk_index"]
        indexes = [
            models.Index(fields=["tenant", "document"]),
            models.Index(fields=["tenant", "document", "page_number"]),
            # HNSW index for ultra-fast approximate cosine similarity search in PostgreSQL
            SafeHnswIndex(
                name="chunk_vector_hnsw_idx",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]
        verbose_name = "Document Chunk"
        verbose_name_plural = "Document Chunks"

    def __str__(self):
        return f"Chunk {self.chunk_index} of {self.document.title} (Page {self.page_number})"
