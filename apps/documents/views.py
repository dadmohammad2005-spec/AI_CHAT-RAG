from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from apps.documents.models import Document, DocumentChunk
from apps.documents.serializers import (
    DocumentSerializer,
    DocumentUploadSerializer,
    DocumentChunkSerializer,
)
from apps.documents.tasks import process_document_pipeline
from apps.core.permissions import HasActiveTenant, IsTenantMember, IsTenantEditor


class DocumentListCreateView(generics.ListCreateAPIView):
    """
    GET /api/v1/documents/: List documents strictly within active tenant context.
    POST /api/v1/documents/upload/: Multi-part file upload with tenant scoping and Celery task dispatch.
    """

    permission_classes = [HasActiveTenant, IsTenantMember]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return DocumentUploadSerializer
        return DocumentSerializer

    def get_queryset(self):
        # Enforce tenant isolation
        return Document.objects.filter(tenant=self.request.tenant).order_by("-created_at")

    def perform_create(self, serializer):
        return serializer.save()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        document = self.perform_create(serializer)
        response_serializer = DocumentSerializer(document, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentUploadView(generics.CreateAPIView):
    """
    Dedicated endpoint: POST /api/v1/documents/upload/
    Handles multi-part upload, assigns tenant, and queues Celery ingestion pipeline.
    """

    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [HasActiveTenant, IsTenantEditor]
    serializer_class = DocumentUploadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        document = serializer.save()
        response_serializer = DocumentSerializer(document, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveDestroyAPIView):
    """
    GET /api/v1/documents/<id>/: Inspect document status, metadata and metrics.
    DELETE /api/v1/documents/<id>/: Remove document and associated vector chunks.
    """

    permission_classes = [HasActiveTenant, IsTenantMember]
    serializer_class = DocumentSerializer

    def get_queryset(self):
        return Document.objects.filter(tenant=self.request.tenant)

    def perform_destroy(self, instance):
        # Subtract storage usage from tenant
        tenant = instance.tenant
        if instance.file_size:
            tenant.storage_bytes_consumed = max(0, tenant.storage_bytes_consumed - instance.file_size)
            tenant.save(update_fields=["storage_bytes_consumed"])

        # Delete physical file
        if instance.file:
            instance.file.delete(save=False)

        instance.delete()


class DocumentChunksListView(generics.ListAPIView):
    """
    GET /api/v1/documents/<id>/chunks/: List chunk slices for debugging or review.
    """

    permission_classes = [HasActiveTenant, IsTenantMember]
    serializer_class = DocumentChunkSerializer

    def get_queryset(self):
        return DocumentChunk.objects.filter(
            tenant=self.request.tenant, document_id=self.kwargs["pk"]
        ).order_by("chunk_index")


class DocumentReprocessView(views.APIView):
    """
    POST /api/v1/documents/<id>/reprocess/: Re-run document parsing and vectorization.
    """

    permission_classes = [HasActiveTenant, IsTenantEditor]

    def post(self, request, pk):
        doc = generics.get_object_or_404(
            Document.objects.filter(tenant=request.tenant), pk=pk
        )
        doc.status = Document.Status.PENDING
        doc.error_message = ""
        doc.save(update_fields=["status", "error_message"])

        process_document_pipeline.delay(str(doc.id))

        return Response(
            {"message": f"Ingestion task queued for '{doc.title}'.", "status": doc.status}
        )
