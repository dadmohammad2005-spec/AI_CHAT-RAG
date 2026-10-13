from django.test import TestCase
from apps.accounts.models import Tenant, CustomUser, Membership
from apps.documents.models import Document, DocumentChunk
from apps.core.context import TenantContext, get_current_tenant


class TenantIsolationTests(TestCase):
    """
    Validates logical database segregation between distinct customer tenants.
    """

    def setUp(self):
        from apps.core.context import set_current_tenant
        set_current_tenant(None)

        self.tenant_a = Tenant.objects.create(name="Tenant Alpha", slug="tenant-alpha")
        self.tenant_b = Tenant.objects.create(name="Tenant Beta", slug="tenant-beta")

        self.user_a = CustomUser.objects.create_user(
            email="alice@alpha.com", password="password123", full_name="Alice Alpha"
        )
        self.user_b = CustomUser.objects.create_user(
            email="bob@beta.com", password="password123", full_name="Bob Beta"
        )

        Membership.objects.create(user=self.user_a, tenant=self.tenant_a, role=Membership.Role.ADMIN)
        Membership.objects.create(user=self.user_b, tenant=self.tenant_b, role=Membership.Role.ADMIN)

        # Create document under Tenant A
        with TenantContext(self.tenant_a):
            self.doc_a = Document.objects.create(
                tenant=self.tenant_a,
                title="Confidential Alpha Financials",
                file_type=Document.FileType.TXT,
                file_size=1024,
                status=Document.Status.READY,
            )
            self.chunk_a = DocumentChunk.objects.create(
                tenant=self.tenant_a,
                document=self.doc_a,
                content="Alpha revenue is 50 million.",
                page_number=1,
                chunk_index=0,
                token_count=10,
            )

        # Create document under Tenant B
        with TenantContext(self.tenant_b):
            self.doc_b = Document.objects.create(
                tenant=self.tenant_b,
                title="Confidential Beta Roadmap",
                file_type=Document.FileType.TXT,
                file_size=2048,
                status=Document.Status.READY,
            )
            self.chunk_b = DocumentChunk.objects.create(
                tenant=self.tenant_b,
                document=self.doc_b,
                content="Beta launching satellite.",
                page_number=1,
                chunk_index=0,
                token_count=10,
            )

    def tearDown(self):
        from apps.core.context import set_current_tenant
        set_current_tenant(None)

    def test_tenant_context_manager(self):
        """Verify TenantContext activates and resets thread/async context."""
        self.assertIsNone(get_current_tenant())
        with TenantContext(self.tenant_a):
            self.assertEqual(get_current_tenant(), self.tenant_a)
        self.assertIsNone(get_current_tenant())

    def test_tenant_manager_isolation(self):
        """
        Verify that querying Document.objects under Tenant A context
        NEVER returns records belonging to Tenant B.
        """
        with TenantContext(self.tenant_a):
            docs = list(Document.objects.all())
            chunks = list(DocumentChunk.objects.all())

            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].id, self.doc_a.id)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].id, self.chunk_a.id)

            # Ensure Tenant B data is invisible
            self.assertFalse(Document.objects.filter(id=self.doc_b.id).exists())
            self.assertFalse(DocumentChunk.objects.filter(id=self.chunk_b.id).exists())

        with TenantContext(self.tenant_b):
            docs = list(Document.objects.all())
            self.assertEqual(len(docs), 1)
            self.assertEqual(docs[0].id, self.doc_b.id)
            self.assertFalse(Document.objects.filter(id=self.doc_a.id).exists())

    def test_unrestricted_manager_access(self):
        """Verify that all_objects bypasses tenant filter for admin/system jobs."""
        with TenantContext(self.tenant_a):
            all_docs = Document.all_objects.all()
            self.assertEqual(all_docs.count(), 2)
