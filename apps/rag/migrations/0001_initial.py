import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="QueryLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("question", models.TextField(help_text="User's natural language question")),
                ("answer", models.TextField(help_text="Generated grounded answer from LLM")),
                ("retrieved_sources", models.JSONField(default=list, help_text="List of source citations with document name, page number, snippet, and similarity score")),
                ("tokens_used", models.IntegerField(default=0, help_text="Total tokens consumed (prompt + completion)")),
                ("latency_ms", models.FloatField(default=0.0, help_text="Round-trip query latency in milliseconds")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("tenant", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="%(app_label)s_%(class)s_set", to="accounts.tenant")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="query_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Query Log",
                "verbose_name_plural": "Query Logs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="querylog",
            index=models.Index(fields=["tenant", "created_at"], name="rag_querylo_tenant__cb6ee6_idx"),
        ),
        migrations.AddIndex(
            model_name="querylog",
            index=models.Index(fields=["tenant", "user"], name="rag_querylo_tenant__ff80aa_idx"),
        ),
    ]
