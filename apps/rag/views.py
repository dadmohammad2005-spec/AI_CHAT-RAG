import logging
from rest_framework import views, generics, status
from rest_framework.response import Response
from apps.rag.serializers import (
    RAGQueryRequestSerializer,
    RAGQueryResponseSerializer,
    QueryLogSerializer,
)
from apps.rag.services import RAGQueryEngine, QuotaExceededException
from apps.rag.models import QueryLog
from apps.core.permissions import HasActiveTenant, IsTenantMember
from apps.core.throttling import TenantRateThrottle

logger = logging.getLogger(__name__)


class RAGQueryAPIView(views.APIView):
    """
    POST /api/v1/chat/query/
    Accepts user question, performs pgvector Cosine similarity search isolated to the
    active tenant, synthesizes prompt with top-K chunks, generates LLM response,
    deducts token quota, and returns grounded answer with page citations.
    """

    permission_classes = [HasActiveTenant, IsTenantMember]
    throttle_classes = [TenantRateThrottle]

    def post(self, request):
        serializer = RAGQueryRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        question = serializer.validated_data["question"]
        top_k = serializer.validated_data.get("top_k", 4)
        document_ids = serializer.validated_data.get("document_ids", [])

        tenant = request.tenant
        user = request.user

        try:
            result = RAGQueryEngine.execute_query(
                tenant=tenant,
                user=user,
                question=question,
                top_k=top_k,
                document_ids=document_ids,
            )
            response_serializer = RAGQueryResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        except QuotaExceededException as qe:
            return Response(
                {
                    "error": "Quota Exceeded",
                    "detail": str(qe),
                    "tokens_consumed": tenant.tokens_consumed,
                    "monthly_limit": tenant.monthly_token_limit,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        except Exception as e:
            logger.exception("Failed to execute RAG query")
            return Response(
                {"error": "Query Processing Error", "detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QueryHistoryListView(generics.ListAPIView):
    """
    GET /api/v1/chat/history/
    Retrieve previous RAG query interactions for the active tenant.
    """

    permission_classes = [HasActiveTenant, IsTenantMember]
    serializer_class = QueryLogSerializer

    def get_queryset(self):
        return QueryLog.objects.filter(tenant=self.request.tenant).order_by("-created_at")[:50]
