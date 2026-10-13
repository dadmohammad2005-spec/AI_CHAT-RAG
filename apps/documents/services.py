import os
import re
import math
import hashlib
import logging
from typing import List, Dict, Any, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


class DocumentExtractor:
    """
    Extracts text and page metadata from PDF, DOCX, TXT, and Markdown files.
    Preserves page boundaries so citations can pinpoint exact page numbers.
    """

    @classmethod
    def extract(cls, file_path: str, file_type: str) -> List[Dict[str, Any]]:
        """
        Returns a list of dicts: [{'page_number': int, 'text': str}]
        """
        file_type = file_type.lower()
        if file_type == "pdf":
            return cls._extract_pdf(file_path)
        elif file_type == "docx":
            return cls._extract_docx(file_path)
        elif file_type in ("txt", "md"):
            return cls._extract_text(file_path)
        else:
            # Fallback to general text extraction
            return cls._extract_text(file_path)

    @classmethod
    def _extract_pdf(cls, file_path: str) -> List[Dict[str, Any]]:
        pages = []
        try:
            import pypdf

            reader = pypdf.PdfReader(file_path)
            for idx, page in enumerate(reader.pages):
                text = page.extract_text() or ""
                clean_text = cls._clean_text(text)
                if clean_text:
                    pages.append({"page_number": idx + 1, "text": clean_text})
        except Exception as e:
            logger.warning(f"pypdf extraction failed on {file_path}, falling back to pdfplumber: {e}")
            try:
                import pdfplumber

                with pdfplumber.open(file_path) as pdf:
                    for idx, page in enumerate(pdf.pages):
                        text = page.extract_text() or ""
                        clean_text = cls._clean_text(text)
                        if clean_text:
                            pages.append({"page_number": idx + 1, "text": clean_text})
            except Exception as e2:
                logger.error(f"pdfplumber also failed on {file_path}: {e2}")
                raise RuntimeError(f"Failed to extract text from PDF: {e2}")

        if not pages:
            # Document may be empty or un-extractable
            pages.append({"page_number": 1, "text": "[No extractable text found in PDF document]"})
        return pages

    @classmethod
    def _extract_docx(cls, file_path: str) -> List[Dict[str, Any]]:
        try:
            import docx

            doc = docx.Document(file_path)
            paragraphs = []
            for p in doc.paragraphs:
                if p.text.strip():
                    paragraphs.append(p.text.strip())

            # Also extract tables
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        paragraphs.append(row_text)

            full_text = "\n\n".join(paragraphs)
            clean_text = cls._clean_text(full_text)

            # In DOCX without explicit page layout, simulate ~500 word pages
            words = clean_text.split()
            page_size = 500
            pages = []
            for i in range(0, len(words), page_size):
                page_words = words[i : i + page_size]
                pages.append({"page_number": (i // page_size) + 1, "text": " ".join(page_words)})

            return pages if pages else [{"page_number": 1, "text": clean_text or "[Empty DOCX]"}]
        except Exception as e:
            logger.error(f"DOCX extraction failed on {file_path}: {e}")
            raise RuntimeError(f"Failed to extract DOCX: {e}")

    @classmethod
    def _extract_text(cls, file_path: str) -> List[Dict[str, Any]]:
        content = ""
        for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                with open(file_path, "r", encoding=encoding) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue

        clean_text = cls._clean_text(content)
        # Check for form feed character \x0c indicating page breaks
        raw_pages = clean_text.split("\x0c")
        pages = []
        for idx, p in enumerate(raw_pages):
            p_text = p.strip()
            if p_text:
                pages.append({"page_number": idx + 1, "text": p_text})

        return pages if pages else [{"page_number": 1, "text": clean_text or "[Empty Text Document]"}]

    @staticmethod
    def _clean_text(text: str) -> str:
        """Normalize line breaks and remove unprintable control characters."""
        if not text:
            return ""
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Replace non-printable characters except newline and tab
        text = re.sub(r"[\x00-\x08\x0b\x0e-\x1f\x7f]", "", text)
        return text.strip()


class DocumentChunker:
    """
    Semantic text chunker adhering to chunk size (e.g. 800 tokens) and overlap (e.g. 100 tokens).
    Maintains exact source page attribution for citations.
    """

    def __init__(self, chunk_size: int = None, chunk_overlap: int = None):
        self.chunk_size = chunk_size or getattr(settings, "RAG_CHUNK_SIZE", 800)
        self.chunk_overlap = chunk_overlap or getattr(settings, "RAG_CHUNK_OVERLAP", 100)

        # Character equivalents assuming ~4 chars per token
        self.char_chunk_size = self.chunk_size * 4
        self.char_chunk_overlap = self.chunk_overlap * 4

    def chunk_pages(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Splits each page's text recursively while preserving page citations.
        Returns: [{'chunk_index': int, 'page_number': int, 'content': str, 'token_count': int}]
        """
        all_chunks = []
        current_index = 0

        for page_data in pages:
            page_num = page_data["page_number"]
            page_text = page_data["text"]

            if not page_text or len(page_text.strip()) == 0:
                continue

            sub_chunks = self._recursive_split(page_text)
            for sub_text in sub_chunks:
                clean_chunk = sub_text.strip()
                if not clean_chunk:
                    continue

                tokens = self.count_tokens(clean_chunk)
                all_chunks.append(
                    {
                        "chunk_index": current_index,
                        "page_number": page_num,
                        "content": clean_chunk,
                        "token_count": tokens,
                    }
                )
                current_index += 1

        return all_chunks

    def _recursive_split(self, text: str) -> List[str]:
        """
        Recursively splits text on natural boundaries: paragraphs -> sentences -> words.
        """
        separators = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]
        return self._split_text_with_separators(text, separators)

    def _split_text_with_separators(self, text: str, separators: List[str]) -> List[str]:
        final_chunks = []
        separator = separators[-1]
        for sep in separators:
            if sep == "":
                separator = ""
                break
            if sep in text:
                separator = sep
                break

        splits = text.split(separator) if separator else list(text)

        good_splits = []
        for s in splits:
            if s:
                good_splits.append(s)

        current_doc = []
        current_len = 0

        for piece in good_splits:
            piece_len = len(piece) + len(separator)
            if current_len + piece_len > self.char_chunk_size and current_doc:
                combined = separator.join(current_doc)
                final_chunks.append(combined)

                # Overlap logic
                overlap_doc = []
                overlap_len = 0
                for item in reversed(current_doc):
                    if overlap_len + len(item) <= self.char_chunk_overlap:
                        overlap_doc.insert(0, item)
                        overlap_len += len(item) + len(separator)
                    else:
                        break
                current_doc = overlap_doc
                current_len = overlap_len

            current_doc.append(piece)
            current_len += piece_len

        if current_doc:
            final_chunks.append(separator.join(current_doc))

        return final_chunks

    @staticmethod
    def count_tokens(text: str) -> int:
        """Calculate token count with tiktoken or fallback estimation."""
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            # Fallback estimation (average 4 chars per token)
            return max(1, len(text) // 4)


class EmbeddingService:
    """
    Service for generating high-dimensional vector embeddings for document chunks and user queries.
    Supports OpenAI API and deterministic offline fallback for local tests and demos.
    """

    DIMENSION = getattr(settings, "AI_EMBEDDING_DIMENSION", 1536)

    @classmethod
    def get_embeddings(cls, texts: List[str]) -> List[List[float]]:
        """Batch embedding generation for optimal throughput."""
        if not texts:
            return []

        api_key = getattr(settings, "OPENAI_API_KEY", "")
        fallback_enabled = getattr(settings, "AI_FALLBACK_TO_MOCK", True)

        if api_key and not api_key.startswith("mock-") and not fallback_enabled:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=api_key)
                model = getattr(settings, "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
                response = client.embeddings.create(input=texts, model=model)
                return [item.embedding for item in response.data]
            except Exception as e:
                logger.error(f"OpenAI embedding generation failed: {e}")
                if not fallback_enabled:
                    raise

        # Deterministic offline mock embedding provider
        return [cls._generate_deterministic_vector(t) for t in texts]

    @classmethod
    def get_embedding(cls, text: str) -> List[float]:
        """Generate embedding for a single text string."""
        return cls.get_embeddings([text])[0]

    @classmethod
    def _generate_deterministic_vector(cls, text: str) -> List[float]:
        """
        Generates a normalized 1536-dimensional float vector derived from the input text hash.
        Guarantees that similar words have reproducible vector representations
        and preserves Cosine distance properties (<=> in PostgreSQL pgvector).
        """
        # Hash text words into dimensions
        vector = [0.0] * cls.DIMENSION
        tokens = re.findall(r"\w+", text.lower())
        if not tokens:
            tokens = ["empty"]

        for i, token in enumerate(tokens):
            h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
            dim_idx = h % cls.DIMENSION
            weight = 1.0 + (1.0 / (i + 1))
            vector[dim_idx] += weight

            # Secondary harmonic
            dim_idx_2 = (h >> 16) % cls.DIMENSION
            vector[dim_idx_2] += weight * 0.5

        # Normalize to unit vector (L2 norm = 1.0)
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [round(v / norm, 6) for v in vector]
        else:
            vector[0] = 1.0

        return vector
