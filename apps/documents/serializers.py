import os
from rest_framework import serializers
from apps.documents.models import Document, DocumentChunk
from apps.documents.tasks import process_document_pipeline


class DocumentChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "page_number",
            "chunk_index",
            "content",
            "token_count",
            "created_at",
        ]
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    file_size_display = serializers.CharField(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "file_url",
            "file_type",
            "file_size",
            "file_size_display",
            "status",
            "error_message",
            "total_chunks",
            "total_pages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "file_url",
            "file_type",
            "file_size",
            "file_size_display",
            "status",
            "error_message",
            "total_chunks",
            "total_pages",
            "created_at",
            "updated_at",
        ]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class DocumentUploadSerializer(serializers.ModelSerializer):
    file = serializers.FileField(required=True)
    title = serializers.CharField(required=False, max_length=255, allow_blank=True)

    ALLOWED_EXTENSIONS = {
        ".pdf": Document.FileType.PDF,
        ".docx": Document.FileType.DOCX,
        ".txt": Document.FileType.TXT,
        ".md": Document.FileType.MD,
    }
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

    class Meta:
        model = Document
        fields = ["id", "title", "file"]
        read_only_fields = ["id"]

    def validate_file(self, value):
        ext = os.path.splitext(value.name)[1].lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            allowed = ", ".join(self.ALLOWED_EXTENSIONS.keys())
            raise serializers.ValidationError(f"Unsupported file format '{ext}'. Allowed formats: {allowed}")

        if value.size > self.MAX_FILE_SIZE:
            raise serializers.ValidationError("File size exceeds 50 MB maximum limit.")

        return value

    def create(self, validated_data):
        file_obj = validated_data["file"]
        ext = os.path.splitext(file_obj.name)[1].lower()
        file_type = self.ALLOWED_EXTENSIONS[ext]

        title = validated_data.get("title")
        if not title:
            # Derive friendly title from filename
            title = os.path.splitext(file_obj.name)[0].replace("_", " ").title()

        request = self.context["request"]
        tenant = request.tenant
        user = request.user if request.user.is_authenticated else None

        document = Document.objects.create(
            tenant=tenant,
            uploaded_by=user,
            title=title,
            file=file_obj,
            file_type=file_type,
            file_size=file_obj.size,
            status=Document.Status.PENDING,
        )

        # Dispatch async ingestion task to Celery
        process_document_pipeline.delay(str(document.id))

        return document
