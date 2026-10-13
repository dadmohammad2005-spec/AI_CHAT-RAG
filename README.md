# Multi-Tenant AI Document Analysis & Query Engine (RAG-based)

A production-grade, enterprise Multi-Tenant Software-as-a-Service (SaaS) application providing asynchronous document parsing, semantic chunking, high-dimensional vector embeddings, and isolated retrieval-augmented generation (RAG) powered by PostgreSQL with the `pgvector` extension, Django 5+, Django REST Framework, Celery, Redis, and a modern Tailwind CSS + Alpine.js + HTMX interface.

---

## 🏗️ Architecture Overview

```
                      +---------------------------------------+
                      |       Web Browser / REST Client       |
                      +---------------------------------------+
                                          |
                      +---------------------------------------+
                      |    TenantContextMiddleware / Auth     |
                      | (Resolves X-Tenant-ID & Session Auth) |
                      +---------------------------------------+
                                          |
                   +----------------------+----------------------+
                   |                                             |
                   v                                             v
       [ Document Upload Flow ]                       [ RAG Query Flow ]
                   |                                             |
       POST /api/v1/documents/upload/                POST /api/v1/chat/query/
                   |                                             |
       +-----------------------+                    +-------------------------+
       | Validate file & store |                    | Validate Tenant Quota   |
       |  Tenant Document row  |                    | & Rate Throttle Limit   |
       +-----------------------+                    +-------------------------+
                   |                                             |
       Dispatch Celery Task                         Generate Query Embedding
       process_document_pipeline                                 |
                   |                                Vector Cosine Search (<=>)
                   v                                DocumentChunk.objects
        +---------------------+                     .filter(tenant=tenant)
        |    Celery Worker    |                     .order_by(CosineDistance)
        +---------------------+                                  |
        | 1. Page extraction  |                     Assemble Grounded Prompt
        |    (PDF/DOCX/TXT)   |                     with Source Page Headers
        | 2. Recursive Chunk  |                                  |
        |    (800t / 100t ov) |                     Invoke LLM Completion
        | 3. Dense Embedding  |                     (OpenAI / Groq / Fallback)
        |    (1536 dims)      |                                  |
        | 4. Bulk INSERT with |                     Deduct Monthly Tokens
        |    pgvector HNSW    |                     & Save Audit QueryLog
        +---------------------+                                  |
                   |                                             v
                   +-------------------------------> Return Answer + Citations
                                                     [Doc Name, Page, Excerpt]
```

---

## 🔑 Key Architectural Capabilities

### 1. Strict Tenant Isolation
- **Context-Bound QuerySets**: Base models inherit from `TenantAwareModel`. The default manager (`TenantManager`) automatically scopes all queries to the active tenant stored in thread-safe and async-safe Python `ContextVar`.
- **Tenant Context Resolution**:
  1. Header `X-Tenant-ID` (UUID or slug).
  2. Session `active_tenant_id`.
  3. Authenticated user's primary tenant membership.
  4. Access verification ensures users cannot impersonate or query tenants they do not belong to.
- **pgvector Hard Boundary**: Vector distance calculations explicitly filter by `tenant_id` at the database level before or during HNSW index traversal:
  ```python
  DocumentChunk.all_objects.filter(
      tenant=tenant,
      document__status=Document.Status.READY,
      embedding__isnull=False,
  ).annotate(
      distance=CosineDistance("embedding", query_vector)
  ).order_by("distance")[:top_k]
  ```

### 2. Non-Blocking Ingestion Pipeline
- Uploads immediately return a `201 Created` response with status `pending`.
- Extraction, chunking, and vector indexing run asynchronously in Celery workers backed by Redis.
- Recursive chunker preserves exact page boundaries so every returned excerpt cites the verified physical page number.

### 3. Usage Quotas & Tiered Rate Limiting
- **Quota Tracking**: Tracks tokens consumed per month against subscription plan allowances (`Free`: 100,000, `Pro`: 1,000,000, `Enterprise`: 10,000,000).
- **Hard Enforcement**: Requests exceeding the tenant quota return `429 Too Many Requests`.
- **Dynamic Rate Throttling**: DRF `TenantRateThrottle` dynamically throttles queries based on the tenant's tier via Redis cache.

---

## 🗄️ Database Schema (PostgreSQL + pgvector)

| Model | Table / Entity | Primary Attributes & Purpose |
|---|---|---|
| `Tenant` | Organization / Customer | `id` (UUID), `name`, `slug`, `plan` (Free/Pro/Enterprise), `monthly_token_limit`, `tokens_consumed`, `storage_bytes_consumed` |
| `CustomUser` | Authentication | `id` (UUID), `email` (unique), `full_name`, `is_active`, `is_staff`, `date_joined` |
| `Membership` | RBAC Mapping | `user` (FK), `tenant` (FK), `role` (`admin`, `editor`, `viewer`), `unique_together(user, tenant)` |
| `Document` | Uploaded File | `tenant` (FK), `title`, `file` (FileField), `file_type`, `file_size`, `status` (`pending`, `processing`, `ready`, `failed`), `total_chunks`, `total_pages` |
| `DocumentChunk` | Semantic Chunk & Vector | `tenant` (FK), `document` (FK), `content` (TextField), `page_number`, `chunk_index`, `embedding` (`VectorField(dim=1536)`), **HNSW Index** |
| `QueryLog` | Audit & Observability | `tenant` (FK), `user` (FK), `question`, `answer`, `retrieved_sources` (JSONField), `tokens_used`, `latency_ms` |

---

## 🚀 Quickstart & Deployment

### Option A: Running via Docker Compose (Recommended)

1. **Clone repository and configure environment variables**:
   ```bash
   cp .env.example .env
   ```

2. **Launch all containers (Database with pgvector, Redis, Django Web, Celery Worker)**:
   ```bash
   docker-compose up --build -d
   ```

3. **Verify running containers**:
   ```bash
   docker-compose ps
   ```

4. **Access the application**:
   - **Frontend UI & Dashboard**: [http://localhost:8000/](http://localhost:8000/)
   - **Django Admin Panel**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
     - Default credentials: `admin@example.com` / `admin123456`
   - **REST API Endpoints**:
     - `GET /api/v1/documents/`
     - `POST /api/v1/documents/upload/`
     - `POST /api/v1/chat/query/`

---

### Option B: Local Development Setup

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Ensure PostgreSQL with pgvector and Redis are running**:
   ```bash
   docker run -d --name pgvector -p 5432:5432 -e POSTGRES_DB=ai_rag_db -e POSTGRES_USER=rag_admin -e POSTGRES_PASSWORD=rag_secure_password pgvector/pgvector:pg16
   docker run -d --name redis -p 6379:6379 redis:7-alpine
   ```

4. **Run migrations and populate sample multi-tenant demo data**:
   ```bash
   python manage.py migrate
   python manage.py setup_demo_data
   ```

5. **Start the Celery worker**:
   ```bash
   celery -A config worker -l info
   ```

6. **Start the Django development server**:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## 📡 REST API Documentation

### 1. Upload Document
- **Endpoint**: `POST /api/v1/documents/upload/`
- **Headers**:
  - `X-Tenant-ID`: `<tenant-uuid-or-slug>`
  - `Content-Type`: `multipart/form-data`
- **Body**:
  - `file`: `<document file (PDF, DOCX, TXT, MD)>`
  - `title` *(optional)*: `Custom Document Title`
- **Response** (`201 Created`):
  ```json
  {
    "id": "c1f729e4-4d8e-4a62-a521-86a01dfb091e",
    "title": "Acme Q3 Financial Report",
    "file_url": "/media/tenants/acme-corp/documents/...",
    "file_type": "pdf",
    "file_size": 248190,
    "file_size_display": "242.4 KB",
    "status": "pending",
    "total_chunks": 0,
    "total_pages": 0,
    "created_at": "2026-10-12T11:40:00Z"
  }
  ```

---

### 2. List Tenant Documents
- **Endpoint**: `GET /api/v1/documents/`
- **Headers**:
  - `X-Tenant-ID`: `<tenant-uuid>`
- **Response** (`200 OK`):
  ```json
  [
    {
      "id": "c1f729e4-4d8e-4a62-a521-86a01dfb091e",
      "title": "Acme Q3 Financial Report",
      "file_type": "pdf",
      "status": "ready",
      "total_chunks": 18,
      "total_pages": 3,
      "created_at": "2026-10-12T11:40:00Z"
    }
  ]
  ```

---

### 3. RAG Query with Page Citations
- **Endpoint**: `POST /api/v1/chat/query/`
- **Headers**:
  - `X-Tenant-ID`: `<tenant-uuid>`
  - `Content-Type`: `application/json`
- **Body**:
  ```json
  {
    "question": "What was the gross revenue and operating margin in Q3?",
    "top_k": 4
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "query_id": "7b36f731-92b1-4f10-b91c-197e415eb6f0",
    "question": "What was the gross revenue and operating margin in Q3?",
    "answer": "Acme Corporation recorded total gross revenue of $142.5 million for the third quarter of 2024 with a net operating margin of 28.2% [Source 1: Acme Q3 Financial Report, Page 1].",
    "citations": [
      {
        "source_id": 1,
        "document_id": "c1f729e4-4d8e-4a62-a521-86a01dfb091e",
        "document_title": "Acme Q3 Financial Report",
        "page_number": 1,
        "chunk_index": 0,
        "similarity_score": 0.9412,
        "similarity_percent": 94.1,
        "excerpt": "Acme Corporation recorded total gross revenue of $142.5 million for the third quarter of 2024, representing an 18.4% year-over-year expansion. Net operating margins improved to 28.2%..."
      }
    ],
    "tokens_used": 128,
    "latency_ms": 34.5,
    "tenant_tokens_consumed": 14328,
    "tenant_tokens_limit": 1000000
  }
  ```

---

## 🧪 Running Automated Tests

Run the full test suite with Django test runner:
```bash
python manage.py test tests/
```

Test coverage includes:
1. `tests/test_tenant_isolation.py`: Cross-tenant data leakage prevention & ORM manager isolation.
2. `tests/test_document_pipeline.py`: Semantic recursive splitting, page numbering, normalized unit embeddings, and Celery tasks.
3. `tests/test_rag_pipeline.py`: pgvector Cosine similarity retrieval, citations extraction, and monthly token quota limit enforcement.
4. `tests/test_api.py`: DRF API endpoints (upload, listing, chat querying).
