from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from rest_framework import status
from apps.accounts.models import Tenant, CustomUser, Membership
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import EmbeddingService


class RAGApiEndpointTests(TestCase):
    """
    Integration tests for DRF REST APIs: documents upload/list and chat query.
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant = Tenant.objects.create(
            name="API Test Tenant",
            slug="api-test-tenant",
            plan=Tenant.Plan.PRO,
            monthly_token_limit=500000,
        )
        self.user = CustomUser.objects.create_user(
            email="dev@apitest.com", password="password123", full_name="API Dev"
        )
        Membership.objects.create(
            user=self.user, tenant=self.tenant, role=Membership.Role.ADMIN
        )

        # Authenticate client with session and DRF token
        self.client.force_login(self.user)
        self.client.force_authenticate(user=self.user)
        session = self.client.session
        session["active_tenant_id"] = str(self.tenant.id)
        session.save()
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.id)}

    def test_document_upload_api(self):
        """Test POST /api/v1/documents/upload/"""
        url = reverse("documents:document-upload")
        file_content = b"Financial report for API testing. Revenue increased 25%."
        uploaded_file = SimpleUploadedFile(
            "test_report.txt", file_content, content_type="text/plain"
        )

        response = self.client.post(
            url,
            {"file": uploaded_file, "title": "API Uploaded Report"},
            format="multipart",
            **self.headers,
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "API Uploaded Report")
        self.assertEqual(response.data["status"], Document.Status.PENDING)

    def test_document_list_api(self):
        """Test GET /api/v1/documents/"""
        Document.all_objects.create(
            tenant=self.tenant,
            title="Listed Document",
            file_type=Document.FileType.TXT,
            status=Document.Status.READY,
        )

        url = reverse("documents:document-list")
        response = self.client.get(url, **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Listed Document")

    def test_chat_query_api(self):
        """Test POST /api/v1/chat/query/"""
        # Create ready document & chunk
        doc = Document.all_objects.create(
            tenant=self.tenant,
            title="Enterprise Cloud Security Guide",
            file_type=Document.FileType.TXT,
            status=Document.Status.READY,
        )
        chunk_text = "TLS 1.3 is enforced on all external API endpoints."
        DocumentChunk.all_objects.create(
            tenant=self.tenant,
            document=doc,
            content=chunk_text,
            page_number=1,
            chunk_index=0,
            token_count=12,
            embedding=EmbeddingService.get_embedding(chunk_text),
        )

        url = reverse("rag:chat-query")
        payload = {"question": "What TLS version is enforced?", "top_k": 2}

        response = self.client.post(url, payload, format="json", **self.headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("answer", response.data)
        self.assertIn("citations", response.data)
        self.assertGreater(len(response.data["citations"]), 0)
        self.assertEqual(
            response.data["citations"][0]["document_title"],
            "Enterprise Cloud Security Guide",
        )
