from rest_framework import serializers
from apps.rag.models import QueryLog


class RAGQueryRequestSerializer(serializers.Serializer):
    question = serializers.CharField(
        required=True,
        min_length=2,
        max_length=4000,
        help_text="Natural language question to ask across indexed tenant documents.",
    )
    top_k = serializers.IntegerField(
        required=False,
        default=4,
        min_value=1,
        max_value=20,
        help_text="Number of most similar semantic chunks to retrieve for context augmentation.",
    )
    document_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        help_text="Optional list of document UUIDs to restrict vector search within.",
    )


class SourceCitationSerializer(serializers.Serializer):
    source_id = serializers.IntegerField()
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    page_number = serializers.IntegerField()
    chunk_index = serializers.IntegerField()
    similarity_score = serializers.FloatField()
    similarity_percent = serializers.FloatField()
    excerpt = serializers.CharField()


class RAGQueryResponseSerializer(serializers.Serializer):
    query_id = serializers.UUIDField()
    question = serializers.CharField()
    answer = serializers.CharField()
    citations = SourceCitationSerializer(many=True)
    tokens_used = serializers.IntegerField()
    latency_ms = serializers.FloatField()
    tenant_tokens_consumed = serializers.IntegerField()
    tenant_tokens_limit = serializers.IntegerField()


class QueryLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = QueryLog
        fields = [
            "id",
            "question",
            "answer",
            "retrieved_sources",
            "tokens_used",
            "latency_ms",
            "created_at",
        ]
        read_only_fields = fields
