import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import apps.documents.models
from pgvector.django import VectorExtension, VectorField, HnswIndex


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        VectorExtension(),
        migrations.CreateModel(
            name="Document",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("file", models.FileField(upload_to=apps.documents.models.tenant_document_upload_path)),
                ("file_type", models.CharField(choices=[("pdf", "PDF Document"), ("docx", "Word Document"), ("txt", "Plain Text"), ("md", "Markdown")], default="pdf", max_length=16)),
                ("file_size", models.BigIntegerField(default=0, help_text="File size in bytes")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("processing", "Processing"), ("ready", "Ready"), ("failed", "Failed")], db_index=True, default="pending", max_length=32)),
                ("error_message", models.TextField(blank=True, default="")),
                ("total_chunks", models.IntegerField(default=0)),
                ("total_pages", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="accounts.tenant")),
                ("uploaded_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="uploaded_documents", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Document",
                "verbose_name_plural": "Documents",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DocumentChunk",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("content", models.TextField(help_text="Extracted text chunk content")),
                ("page_number", models.IntegerField(default=1, help_text="1-based page number for exact citation")),
                ("chunk_index", models.IntegerField(default=0, help_text="Sequence index within the document")),
                ("token_count", models.IntegerField(default=0)),
                ("embedding", VectorField(blank=True, dimensions=1536, help_text="Dense vector representation (e.g., OpenAI text-embedding-3-small)", null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="documents.document")),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="accounts.tenant")),
            ],
            options={
                "verbose_name": "Document Chunk",
                "verbose_name_plural": "Document Chunks",
                "ordering": ["document", "chunk_index"],
            },
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["tenant", "status"], name="documents_d_tenant__b13dd9_idx"),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(fields=["tenant", "created_at"], name="documents_d_tenant__88523c_idx"),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=models.Index(fields=["tenant", "document"], name="documents_d_tenant__64a784_idx"),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=models.Index(fields=["tenant", "document", "page_number"], name="documents_d_tenant__1cfbca_idx"),
        ),
        migrations.AddIndex(
            model_name="documentchunk",
            index=apps.documents.models.SafeHnswIndex(ef_construction=64, fields=["embedding"], m=16, name="chunk_vector_hnsw_idx", opclasses=["vector_cosine_ops"]),
        ),
    ]
