import math
from django.test import TestCase
from django.core.files.base import ContentFile
from apps.accounts.models import Tenant
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import DocumentExtractor, DocumentChunker, EmbeddingService
from apps.documents.tasks import process_document_pipeline


class DocumentPipelineTests(TestCase):
    """
    Tests document parsing, recursive chunking, embedding generation, and Celery tasks.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Pipeline Test Tenant", slug="pipeline-test")

    def test_document_chunker_page_preservation(self):
        """Verify chunker respects page boundaries and calculates tokens."""
        pages = [
            {"page_number": 1, "text": "This is page one text. It discusses financial metrics in detail."},
            {"page_number": 2, "text": "This is page two text. It discusses infrastructure and security."},
        ]

        chunker = DocumentChunker(chunk_size=100, chunk_overlap=20)
        chunks = chunker.chunk_pages(pages)

        self.assertGreaterEqual(len(chunks), 2)
        # Check first chunk has page 1
        self.assertEqual(chunks[0]["page_number"], 1)
        self.assertIn("page one", chunks[0]["content"])

        # Check subsequent chunk has page 2
        page_2_chunk = next(c for c in chunks if c["page_number"] == 2)
        self.assertIn("page two", page_2_chunk["content"])

    def test_embedding_service_dimensions_and_norm(self):
        """Verify generated embeddings are normalized 1536-dimensional vectors."""
        text = "Acme enterprise document intelligence with pgvector."
        vector = EmbeddingService.get_embedding(text)

        self.assertEqual(len(vector), 1536)
        # Check unit L2 norm (magnitude ~= 1.0)
        magnitude = math.sqrt(sum(v * v for v in vector))
        self.assertAlmostEqual(magnitude, 1.0, places=3)

    def test_batch_embeddings(self):
        texts = ["First document paragraph", "Second document paragraph"]
        vectors = EmbeddingService.get_embeddings(texts)

        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 1536)
        self.assertEqual(len(vectors[1]), 1536)

    def test_process_document_pipeline_task(self):
        """Verify Celery task pipeline from PENDING to READY."""
        sample_text = "Page 1: Acme overview.\x0cPage 2: Acme detailed cloud architecture."
        doc = Document(
            tenant=self.tenant,
            title="Sample Pipeline Document",
            file_type=Document.FileType.TXT,
            file_size=len(sample_text),
            status=Document.Status.PENDING,
        )
        doc.file.save("sample.txt", ContentFile(sample_text.encode("utf-8")), save=False)
        doc.save()

        # Run pipeline task synchronously
        result = process_document_pipeline(str(doc.id))

        doc.refresh_from_db()
        self.assertEqual(doc.status, Document.Status.READY)
        self.assertGreater(doc.total_chunks, 0)
        self.assertEqual(doc.total_pages, 2)
        self.assertEqual(result["status"], "success")

        # Verify chunks saved to database
        chunks = DocumentChunk.all_objects.filter(document=doc)
        self.assertEqual(chunks.count(), doc.total_chunks)
        self.assertIsNotNone(chunks.first().embedding)
