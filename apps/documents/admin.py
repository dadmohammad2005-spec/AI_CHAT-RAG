from django.contrib import admin
from apps.documents.models import Document, DocumentChunk


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "tenant",
        "file_type",
        "file_size_display",
        "status",
        "total_chunks",
        "total_pages",
        "created_at",
    )
    search_fields = ("title", "tenant__name")
    list_filter = ("status", "file_type", "created_at")
    readonly_fields = ("id", "created_at", "updated_at", "total_chunks", "total_pages")


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "tenant", "page_number", "chunk_index", "token_count")
    search_fields = ("document__title", "content")
    list_filter = ("page_number", "tenant")
    readonly_fields = ("id", "created_at")
