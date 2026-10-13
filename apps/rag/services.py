import time
import logging
from typing import List, Dict, Any, Optional
from django.conf import settings
from pgvector.django import CosineDistance
from apps.documents.models import Document, DocumentChunk
from apps.documents.services import EmbeddingService, DocumentChunker
from apps.rag.models import QueryLog

logger = logging.getLogger(__name__)


class QuotaExceededException(Exception):
    """Raised when tenant has depleted their allocated monthly token allowance."""
    pass


class RAGQueryEngine:
    """
    Core RAG Engine orchestrating:
    1. Tenant quota validation
    2. Query embedding generation
    3. pgvector Cosine similarity search (<=> operator) scoped to tenant
    4. Context synthesis with source citations
    5. LLM inference (OpenAI / Groq / Fallback synthesizer)
    6. Token accounting and audit logging
    """

    SYSTEM_PROMPT = (
        "You are an expert AI enterprise analyst. Your task is to answer the user's question "
        "truthfully and accurately, relying EXCLUSIVELY on the provided document excerpts below.\n\n"
        "Rules:\n"
        "1. Direct Citations: Whenever you state a fact derived from the text, cite the source using "
        "the format: [Source X: Document Title, Page Y].\n"
        "2. Groundedness: Do not speculate or make up information. If the context does not contain "
        "sufficient information to answer the question, state clearly: "
        "'Based on the uploaded documents for this tenant, I could not find information to answer this question.'\n"
        "3. Tone: Be professional, concise, and structured in your explanations."
    )

    @classmethod
    def execute_query(
        cls,
        tenant,
        user,
        question: str,
        top_k: int = None,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        top_k = top_k or getattr(settings, "RAG_TOP_K", 4)

        # 1. Enforce Tenant Token Quota
        if not tenant.has_quota(requested_tokens=50):
            raise QuotaExceededException(
                f"Tenant '{tenant.name}' has exceeded its monthly token quota "
                f"({tenant.tokens_consumed:,} / {tenant.monthly_token_limit:,} tokens used). "
                f"Please upgrade your plan to continue querying."
            )

        # 2. Generate Query Embedding
        query_vector = EmbeddingService.get_embedding(question)

        # 3. Vector Similarity Search strictly isolated to the active tenant
        base_queryset = DocumentChunk.all_objects.filter(
            tenant=tenant,
            document__status=Document.Status.READY,
            embedding__isnull=False,
        ).select_related("document")

        if document_ids:
            base_queryset = base_queryset.filter(document_id__in=document_ids)

        from django.db import connection

        if connection.vendor == "postgresql":
            # CosineDistance corresponds to pgvector's `<=>` operator
            retrieved_chunks = list(
                base_queryset.annotate(distance=CosineDistance("embedding", query_vector))
                .order_by("distance")[:top_k]
            )
        else:
            # Python-based Cosine distance fallback for SQLite / local testing
            all_candidate_chunks = list(base_queryset)

            def _calc_dist(c):
                emb = c.embedding
                if not emb:
                    return 1.0
                if isinstance(emb, str):
                    import json
                    try:
                        emb = json.loads(emb)
                    except Exception:
                        return 1.0
                dot = sum(a * b for a, b in zip(emb, query_vector))
                return max(0.0, 1.0 - dot)

            all_candidate_chunks.sort(key=_calc_dist)
            retrieved_chunks = all_candidate_chunks[:top_k]
            for c in retrieved_chunks:
                c.distance = _calc_dist(c)

        # Format source citations
        citations = []
        context_blocks = []

        for idx, chunk in enumerate(retrieved_chunks, start=1):
            doc_title = chunk.document.title
            page_num = chunk.page_number
            # Cosine similarity = 1 - Cosine distance
            cosine_similarity = max(0.0, 1.0 - float(chunk.distance))
            similarity_percent = round(cosine_similarity * 100, 1)

            citation_item = {
                "source_id": idx,
                "document_id": str(chunk.document.id),
                "document_title": doc_title,
                "page_number": page_num,
                "chunk_index": chunk.chunk_index,
                "similarity_score": round(cosine_similarity, 4),
                "similarity_percent": similarity_percent,
                "excerpt": chunk.content.strip(),
            }
            citations.append(citation_item)

            context_blocks.append(
                f"--- [Source {idx}: \"{doc_title}\", Page {page_num}] ---\n{chunk.content.strip()}\n"
            )

        formatted_context = "\n".join(context_blocks)

        # 4. Invoke LLM Generation
        answer, prompt_tokens, completion_tokens = cls._generate_llm_response(
            question, formatted_context, citations
        )

        total_tokens = prompt_tokens + completion_tokens
        elapsed_ms = round((time.time() - start_time) * 1000, 2)

        # 5. Atomically update Tenant Token Consumption
        tenant.consume_tokens(total_tokens)

        # 6. Record Audit QueryLog
        query_log = QueryLog.all_objects.create(
            tenant=tenant,
            user=user if (user and user.is_authenticated) else None,
            question=question,
            answer=answer,
            retrieved_sources=citations,
            tokens_used=total_tokens,
            latency_ms=elapsed_ms,
        )

        return {
            "query_id": str(query_log.id),
            "question": question,
            "answer": answer,
            "citations": citations,
            "tokens_used": total_tokens,
            "latency_ms": elapsed_ms,
            "tenant_tokens_consumed": tenant.tokens_consumed,
            "tenant_tokens_limit": tenant.monthly_token_limit,
        }

    @classmethod
    def _generate_llm_response(
        cls, question: str, context: str, citations: List[Dict[str, Any]]
    ) -> (str, int, int):
        """
        Sends grounded context + user prompt to LLM (OpenAI / Groq)
        or runs deterministic grounded synthesizer when offline.
        """
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        fallback_enabled = getattr(settings, "AI_FALLBACK_TO_MOCK", True)

        if api_key and not api_key.startswith("mock-") and not fallback_enabled:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=api_key)
                model = getattr(settings, "OPENAI_CHAT_MODEL", "gpt-4o-mini")

                user_prompt = (
                    f"CONTEXT INFORMATION:\n{context}\n\n"
                    f"USER QUESTION: {question}\n\n"
                    f"Provide an accurate answer supported by citations from the context above."
                )

                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": cls.SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                )

                answer = response.choices[0].message.content or ""
                usage = response.usage
                prompt_tokens = usage.prompt_tokens if usage else DocumentChunker.count_tokens(user_prompt)
                completion_tokens = (
                    usage.completion_tokens if usage else DocumentChunker.count_tokens(answer)
                )

                return answer, prompt_tokens, completion_tokens
            except Exception as e:
                logger.error(f"OpenAI completion call failed: {e}")
                if not fallback_enabled:
                    raise

        # Offline deterministic grounded synthesis
        return cls._synthesize_offline_answer(question, context, citations)

    @classmethod
    def _synthesize_offline_answer(
        cls, question: str, context: str, citations: List[Dict[str, Any]]
    ) -> (str, int, int):
        """
        Deterministic, offline answer generator for development and testing.
        Extracts relevant sentences from top matched citations and builds structured markdown.
        """
        if not citations or not context.strip():
            answer = (
                "Based on the uploaded documents for this tenant, I could not find any relevant "
                "information to answer your question."
            )
            p_tokens = DocumentChunker.count_tokens(question) + 50
            c_tokens = DocumentChunker.count_tokens(answer)
            return answer, p_tokens, c_tokens

        top_citation = citations[0]
        excerpt = top_citation["excerpt"]

        # Extract most relevant sentences matching question keywords
        keywords = set(re_word.lower() for re_word in question.split() if len(re_word) > 3)
        sentences = [s.strip() for s in excerpt.replace("\n", " ").split(".") if len(s.strip()) > 10]

        matched_sentences = []
        for s in sentences:
            if any(kw in s.lower() for kw in keywords):
                matched_sentences.append(s)

        highlight_content = ". ".join(matched_sentences[:3]) if matched_sentences else sentences[0] if sentences else excerpt[:200]

        answer = (
            f"Based on **{top_citation['document_title']}** (Page {top_citation['page_number']}), "
            f"the following key information was identified:\n\n"
            f"> \"{highlight_content}.\"\n\n"
            f"This addresses your query regarding *\"{question}\"* "
            f"[Source {top_citation['source_id']}: {top_citation['document_title']}, Page {top_citation['page_number']}]."
        )

        p_tokens = DocumentChunker.count_tokens(question + context)
        c_tokens = DocumentChunker.count_tokens(answer)
        return answer, p_tokens, c_tokens
