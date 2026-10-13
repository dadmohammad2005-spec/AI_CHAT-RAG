from django.test import TestCase
from apps.accounts.models import Tenant, CustomUser, Membership
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import EmbeddingService
from apps.rag.services import RAGQueryEngine, QuotaExceededException
from apps.rag.models import QueryLog
from apps.core.context import TenantContext


class RAGPipelineTests(TestCase):
    """
    Tests vector retrieval, source citations, token quotas, and audit logging.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Acme RAG Test Corp",
            slug="acme-rag-test",
            plan=Tenant.Plan.PRO,
            monthly_token_limit=10000,
            tokens_consumed=0,
        )
        self.other_tenant = Tenant.objects.create(
            name="Competitor Corp",
            slug="competitor-corp",
            monthly_token_limit=10000,
            tokens_consumed=0,
        )

        self.user = CustomUser.objects.create_user(
            email="researcher@acme.com", password="password123", full_name="AI Researcher"
        )
        Membership.objects.create(user=self.user, tenant=self.tenant, role=Membership.Role.ADMIN)

        # Seed indexed document for Acme
        with TenantContext(self.tenant):
            self.acme_doc = Document.objects.create(
                tenant=self.tenant,
                title="Acme Q3 Financial Report",
                file_type=Document.FileType.TXT,
                status=Document.Status.READY,
                file_size=5000,
                total_pages=1,
            )
            acme_text = "Acme Corporation gross revenue hit 142.5 million dollars in Q3 with 28% margin."
            self.acme_chunk = DocumentChunk.objects.create(
                tenant=self.tenant,
                document=self.acme_doc,
                content=acme_text,
                page_number=1,
                chunk_index=0,
                token_count=18,
                embedding=EmbeddingService.get_embedding(acme_text),
            )

        # Seed indexed document for Competitor
        with TenantContext(self.other_tenant):
            self.comp_doc = Document.objects.create(
                tenant=self.other_tenant,
                title="Competitor Secret Patent",
                file_type=Document.FileType.TXT,
                status=Document.Status.READY,
                file_size=5000,
                total_pages=1,
            )
            comp_text = "Competitor secret blueprint for neural matrix."
            self.comp_chunk = DocumentChunk.objects.create(
                tenant=self.other_tenant,
                document=self.comp_doc,
                content=comp_text,
                page_number=1,
                chunk_index=0,
                token_count=15,
                embedding=EmbeddingService.get_embedding(comp_text),
            )

    def test_rag_query_execution_and_citations(self):
        """Verify vector search returns citations and updates tokens."""
        result = RAGQueryEngine.execute_query(
            tenant=self.tenant,
            user=self.user,
            question="What was Acme's gross revenue in Q3?",
            top_k=2,
        )

        self.assertIn("answer", result)
        self.assertGreater(len(result["citations"]), 0)

        top_citation = result["citations"][0]
        self.assertEqual(top_citation["document_title"], "Acme Q3 Financial Report")
        self.assertEqual(top_citation["page_number"], 1)
        self.assertIn("142.5 million", top_citation["excerpt"])

        # Check token consumption updated
        self.tenant.refresh_from_db()
        self.assertGreater(self.tenant.tokens_consumed, 0)
        self.assertEqual(result["tokens_used"], self.tenant.tokens_consumed)

        # Check QueryLog created
        log = QueryLog.all_objects.filter(id=result["query_id"]).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.tenant, self.tenant)
        self.assertEqual(log.user, self.user)

    def test_rag_strict_tenant_isolation(self):
        """
        Verify that searching under Acme tenant NEVER returns chunks
        belonging to Competitor Corp.
        """
        result = RAGQueryEngine.execute_query(
            tenant=self.tenant,
            user=self.user,
            question="What is the secret blueprint for neural matrix?",
            top_k=5,
        )

        for citation in result["citations"]:
            self.assertNotEqual(citation["document_title"], "Competitor Secret Patent")
            self.assertEqual(citation["document_id"], str(self.acme_doc.id))

    def test_token_quota_limit_enforcement(self):
        """Verify QuotaExceededException is raised when tokens are exhausted."""
        self.tenant.tokens_consumed = self.tenant.monthly_token_limit
        self.tenant.save()

        with self.assertRaises(QuotaExceededException):
            RAGQueryEngine.execute_query(
                tenant=self.tenant,
                user=self.user,
                question="Any new question?",
                top_k=2,
            )
