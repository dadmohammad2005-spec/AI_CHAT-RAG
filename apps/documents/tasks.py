import logging
import traceback

try:
    from celery import shared_task
except ImportError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            def wrapper(*a, **kw):
                return fn(None, *a, **kw)
            wrapper.delay = wrapper
            return wrapper
        return decorator

from django.db import transaction
from django.conf import settings
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import DocumentExtractor, DocumentChunker, EmbeddingService
from apps.core.context import TenantContext

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_document_pipeline(self, document_id: str):
    """
    Celery asynchronous ingestion task for documents:
    1. Fetch Document & set status to PROCESSING.
    2. Extract text & page metadata (PDF / DOCX / TXT).
    3. Recursively chunk text (800 tokens, 100 token overlap).
    4. Generate embeddings in batches.
    5. Bulk-insert DocumentChunk rows with vectors into pgvector PostgreSQL.
    6. Update Document status to READY (or FAILED on error).
    """
    logger.info(f"Starting ingestion pipeline for document_id={document_id}")

    try:
        document = Document.all_objects.select_related("tenant").get(id=document_id)
    except Document.DoesNotExist:
        logger.error(f"Document with ID {document_id} not found.")
        return {"status": "error", "message": "Document not found"}

    # Scoped execution under the document's tenant context
    with TenantContext(document.tenant):
        try:
            # 1. Update status to processing
            document.status = Document.Status.PROCESSING
            document.error_message = ""
            document.save(update_fields=["status", "error_message", "updated_at"])

            # Remove any previous chunks if this is a re-run
            DocumentChunk.all_objects.filter(document=document).delete()

            file_path = document.file.path
            file_type = document.file_type or "pdf"

            # 2. Extract raw text with page metadata
            logger.info(f"Extracting text from {file_path} (type: {file_type})")
            pages = DocumentExtractor.extract(file_path, file_type)
            total_pages = len(pages)

            # 3. Chunk text recursively with overlap
            logger.info(f"Chunking text across {total_pages} extracted pages")
            chunker = DocumentChunker(
                chunk_size=getattr(settings, "RAG_CHUNK_SIZE", 800),
                chunk_overlap=getattr(settings, "RAG_CHUNK_OVERLAP", 100),
            )
            raw_chunks = chunker.chunk_pages(pages)

            if not raw_chunks:
                raise ValueError("No text content could be extracted or chunked from document.")

            logger.info(f"Generated {len(raw_chunks)} chunks. Generating embeddings in batches...")

            # 4. Generate embeddings in batches
            batch_size = 50
            chunk_instances = []

            for i in range(0, len(raw_chunks), batch_size):
                batch = raw_chunks[i : i + batch_size]
                batch_texts = [item["content"] for item in batch]
                batch_embeddings = EmbeddingService.get_embeddings(batch_texts)

                for chunk_data, emb in zip(batch, batch_embeddings):
                    chunk_obj = DocumentChunk(
                        tenant=document.tenant,
                        document=document,
                        content=chunk_data["content"],
                        page_number=chunk_data["page_number"],
                        chunk_index=chunk_data["chunk_index"],
                        token_count=chunk_data["token_count"],
                        embedding=emb,
                    )
                    chunk_instances.append(chunk_obj)

            # 5. Bulk create DocumentChunk records with vectors
            logger.info(f"Bulk-saving {len(chunk_instances)} DocumentChunk instances with pgvector...")
            with transaction.atomic():
                DocumentChunk.all_objects.bulk_create(chunk_instances, batch_size=250)

                # 6. Update document status to READY
                document.status = Document.Status.READY
                document.total_chunks = len(chunk_instances)
                document.total_pages = total_pages
                document.save(
                    update_fields=[
                        "status",
                        "total_chunks",
                        "total_pages",
                        "updated_at",
                    ]
                )

                # Increment tenant storage consumption
                tenant = document.tenant
                tenant.storage_bytes_consumed += document.file_size
                tenant.save(update_fields=["storage_bytes_consumed"])

            logger.info(f"Document {document.id} processed successfully: {len(chunk_instances)} chunks created.")
            return {
                "status": "success",
                "document_id": str(document.id),
                "chunks_created": len(chunk_instances),
                "pages": total_pages,
            }

        except Exception as exc:
            error_trace = traceback.format_exc()
            logger.error(f"Error processing document {document_id}: {error_trace}")
            document.status = Document.Status.FAILED
            document.error_message = str(exc)
            document.save(update_fields=["status", "error_message", "updated_at"])
            raise self.retry(exc=exc, countdown=15)
