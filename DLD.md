# noRAGDocQuery — Detailed Low Level Design (DLD)

**Project:** noRAGDocQuery  
**Repo:** apurva-ship-it/noragdocquery-backend  
**Version:** 1.0.0  
**Last updated:** 2026-05-12  
**Author:** PDLC Pipeline · Implemented by Claude Sonnet 4.6

---

## Table of Contents

1. [Overview](#1-overview)
2. [Model & Technology Stack](#2-model--technology-stack)
3. [Why No RAG](#3-why-no-rag)
4. [High Level Architecture](#4-high-level-architecture)
5. [Project Structure](#5-project-structure)
6. [Data Model](#6-data-model)
7. [Module Responsibilities](#7-module-responsibilities)
8. [API Contracts](#8-api-contracts)
9. [Document Parsing Pipeline](#9-document-parsing-pipeline)
10. [Chunking Algorithm](#10-chunking-algorithm)
11. [Wiki Assembly & Token Trimming](#11-wiki-assembly--token-trimming)
12. [LLM Integration (SSE Streaming)](#12-llm-integration-sse-streaming)
13. [Configuration Reference](#13-configuration-reference)
14. [Dependency Graph](#14-dependency-graph)
15. [Error Handling Matrix](#15-error-handling-matrix)
16. [RAG vs noRAGDocQuery](#16-rag-vs-noragdocquery)
17. [Running Locally](#17-running-locally)
18. [Testing](#18-testing)

---

## 1. Overview

noRAGDocQuery is a public web application that allows anonymous users to upload documents (PDF, DOCX, DOC, XLSX, XLS, TXT) and query their contents using a Large Language Model. It deliberately avoids vector databases, embeddings, and similarity search — all document text is stored as plain chunks in SQLite and assembled into a single context window ("wiki") at query time.

**Core user flow:**
```
Upload documents → Text extracted & chunked → Stored in SQLite
                                                      ↓
                              User asks question → All chunks assembled into wiki
                                                      ↓
                              Wiki + question sent to LLM → Answer streamed back
```

---

## 2. Model & Technology Stack

### LLM Models

| Usage | Model | Provider |
|---|---|---|
| Code generation (this codebase) | Claude Sonnet 4.6 (`claude-sonnet-4-6`) | Anthropic (via Claude Code CLI) |
| Runtime query answering | `openai/gpt-4o-mini` (default, configurable) | OpenRouter API |
| PDLC spec / architecture | `openai/gpt-oss-120b:free` | OpenRouter (pipeline only) |

### Backend Tech Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.9+ | Runtime |
| Web Framework | FastAPI | 0.115.0 | REST API + SSE streaming |
| ASGI Server | Uvicorn | 0.30.6 | Production HTTP server |
| ORM | SQLAlchemy | 2.0.35 | Database access (sync) |
| Migrations | Alembic | 1.13.3 | Schema versioning |
| Database | SQLite | stdlib | Persistent chunk storage |
| Config | pydantic-settings | 2.5.2 | `.env` → typed Settings object |
| Validation | Pydantic v2 | 2.9.2 | Request/response schemas |
| HTTP Client | httpx | 0.27.2 | Async OpenRouter calls + SSE relay |
| File Upload | python-multipart | 0.0.12 | Multipart form parsing |
| PDF Parser | PyMuPDF (`fitz`) | 1.24.11 | PDF text extraction per page |
| DOCX Parser | python-docx | 1.1.2 | Word document paragraph extraction |
| XLSX Parser | openpyxl | 3.1.5 | Excel (.xlsx) cell value extraction |
| XLS Parser | xlrd | 2.0.1 | Legacy Excel (.xls) |
| Testing | pytest + pytest-asyncio | 8.3.3 | Unit + integration tests |

---

## 3. Why No RAG

**RAG (Retrieval Augmented Generation)** works by:
1. Converting text chunks into vector embeddings
2. Storing embeddings in a vector DB (Chroma, FAISS, pgvector, etc.)
3. At query time, embedding the question and running similarity search to find top-K relevant chunks
4. Sending only those chunks to the LLM

**noRAGDocQuery** skips all of that:

| Concern | RAG approach | noRAGDocQuery approach |
|---|---|---|
| Chunking | Semantic / sentence-aware | Fixed 1000-char slices |
| Storage | Vector DB with embedding column | SQLite plain `TEXT` rows |
| Retrieval | Cosine similarity search | `SELECT * ORDER BY id` |
| Context sent to LLM | Top-K most relevant chunks | All chunks (token-budget trimmed) |
| Accuracy on large docs | High — only relevant parts | Degrades beyond ~32K chars |
| Infrastructure | Embedding model + vector index | Zero — pure SQL |
| Best suited for | Large corpora, precision retrieval | Small–medium docs, zero setup |

**Trade-off in plain terms:** RAG *searches* your documents before answering. noRAGDocQuery *reads everything* every time. It works well because modern LLMs have large context windows — as long as total document text fits within the 8000-token budget (~32 pages), the LLM sees everything and answers accurately. Beyond that, the oldest content is silently dropped from the context.

---

## 4. High Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client (Browser)                            │
│                    React SPA — localhost:5173                       │
└────────────┬────────────────────────────────┬───────────────────────┘
             │ multipart/form-data            │ application/json
             │ POST /api/upload               │ POST /api/query
             │                GET /api/documents                      │
             ▼                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend — localhost:8000                  │
│                                                                     │
│  ┌──────────────┐   ┌──────────────────┐   ┌───────────────────┐   │
│  │  /api/upload │   │  /api/documents  │   │   /api/query      │   │
│  │  (routers/   │   │  (routers/       │   │   (routers/       │   │
│  │  upload.py)  │   │  documents.py)   │   │   query.py)  SSE  │   │
│  └──────┬───────┘   └────────┬─────────┘   └────────┬──────────┘   │
│         │                    │                       │              │
│         ▼                    ▼                       │              │
│  ┌─────────────────────────────────────────┐         │              │
│  │       Parsing & Chunking Service        │         │              │
│  │       parsers.py                        │         │              │
│  │  PDF→fitz  DOCX→python-docx             │         │              │
│  │  XLSX→openpyxl  XLS→xlrd  TXT→decode   │         │              │
│  │  → 1000-char chunks, sanitized          │         │              │
│  └──────────────────┬──────────────────────┘         │              │
│                     │                                 │              │
│         ┌───────────▼─────────────────────────────────▼──────────┐  │
│         │              SQLAlchemy ORM (sync)                      │  │
│         │              document_chunks table                      │  │
│         └───────────────────────┬──────────────────────────────  ┘  │
│                                 ▼                                    │
│         ┌───────────────────────────────────────────────────────┐   │
│         │            SQLite — noragdocquery.db                   │   │
│         └───────────────────────────────────────────────────────┘   │
│                                                                      │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │              Wiki Assembly + LLM Bridge (query.py)            │  │
│  │  SELECT chunks ORDER BY id → trim to 8k token budget          │  │
│  │  httpx async stream → OpenRouter /chat/completions            │  │
│  │  SSE relay: data: {"token": "..."} to client                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                    │ HTTPS + SSE
                                    ▼
              ┌────────────────────────────────────────┐
              │   OpenRouter API                       │
              │   POST /chat/completions?stream=true   │
              │   model: openai/gpt-4o-mini (default)  │
              └────────────────────────────────────────┘
```

---

## 5. Project Structure

```
backend/
├── __init__.py
├── main.py                          # FastAPI app factory, CORS, lifespan
├── config.py                        # Settings(BaseSettings), lru_cache singleton
├── database.py                      # SQLAlchemy engine, SessionLocal, Base, get_db()
├── models.py                        # DocumentChunk ORM model (SQLAlchemy 2.0)
├── schemas.py                       # Pydantic v2 request/response schemas
├── parsers.py                       # Format parsers + extract_and_chunk() dispatcher
├── requirements.txt
├── alembic.ini
├── .gitignore
├── DLD.md                           # ← this file
├── alembic/
│   ├── env.py                       # Alembic migration environment
│   └── versions/
│       └── 0001_create_document_chunks.py   # Initial schema migration
├── routers/
│   ├── __init__.py
│   ├── upload.py                    # POST /api/upload
│   ├── documents.py                 # GET /api/documents
│   └── query.py                     # POST /api/query (SSE streaming)
└── tests/
    ├── __init__.py
    ├── conftest.py                  # pytest fixtures, test DB setup/teardown
    └── test_upload.py               # Upload + documents endpoint tests
```

---

## 6. Data Model

### `document_chunks` table

```sql
CREATE TABLE document_chunks (
    id            INTEGER      PRIMARY KEY AUTOINCREMENT,
    document_name VARCHAR(255) NOT NULL,
    chunk_text    TEXT         NOT NULL,
    chunk_index   INTEGER      NOT NULL,
    uploaded_at   DATETIME     NOT NULL
);

CREATE INDEX ix_document_chunks_document_name ON document_chunks (document_name);
```

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | Auto-incrementing row ID — also serves as global insertion order |
| `document_name` | VARCHAR(255) | Original filename as uploaded (e.g. `report.pdf`) |
| `chunk_text` | TEXT | 1000-char sanitized text slice |
| `chunk_index` | INTEGER | Position of this chunk within its document (0-based) |
| `uploaded_at` | DATETIME | UTC timestamp of the upload batch |

**No embedding column. No vector. No similarity index.**

### SQLAlchemy ORM mapping (`models.py`)

```python
class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id:            Mapped[int]      # PK, autoincrement
    document_name: Mapped[str]      # VARCHAR(255), indexed
    chunk_text:    Mapped[str]      # TEXT
    chunk_index:   Mapped[int]      # INTEGER
    uploaded_at:   Mapped[datetime] # DATETIME, UTC
```

Uses SQLAlchemy 2.0 `Mapped` + `mapped_column` style throughout.

---

## 7. Module Responsibilities

### `main.py` — App Factory

- Creates `FastAPI` instance with title and version
- Registers `CORSMiddleware` (allows `localhost:5173` and `localhost:3000`)
- `lifespan` context manager calls `Base.metadata.create_all()` on startup (creates tables if not exists — Alembic handles versioned migrations in production)
- Includes all three routers under `/api` prefix

### `config.py` — Settings

- `Settings(BaseSettings)` reads all config from environment / `.env` file
- `@lru_cache(maxsize=1)` ensures a single instance for the process lifetime
- All tunable values (chunk size, token budget, model name) live here — no magic numbers in business logic

### `database.py` — DB Session

- Creates a single `engine` from `settings.database_url`
- `check_same_thread=False` required for SQLite with FastAPI's sync ORM
- `get_db()` is a FastAPI dependency that yields a `Session` and guarantees `db.close()` on exit via `finally`

### `models.py` — ORM Model

- Single model: `DocumentChunk`
- `uploaded_at` defaults to `datetime.now(timezone.utc)` via a callable default (not `datetime.utcnow` — avoids naive datetime deprecation)

### `schemas.py` — Pydantic Schemas

```
DocumentSummary    — document_name, total_characters, chunk_count
UploadResponse     — documents: list[DocumentSummary]
QueryRequest       — question: str
DocumentChunkSchema — id, document_name, chunk_index, uploaded_at (ORM-mapped)
```

All response schemas use `model_config = {"from_attributes": True}` for ORM compatibility.

### `parsers.py` — Parsing Service

- Zero FastAPI / SQLAlchemy imports — pure functions, easily unit-testable
- `extract_and_chunk(filename, content)` is the single public entry point
- Raises typed exceptions (`UnsupportedFormatError`, `FileTooLargeError`) that routers map to HTTP status codes
- `_PARSERS` dict dispatches by file extension

### `routers/upload.py` — POST /api/upload

- Accepts `list[UploadFile]` (multiple files in one request)
- For each file: read bytes → parse → chunk → bulk insert → accumulate summary
- `db.bulk_save_objects()` inserts all chunks for one file in a single transaction
- Returns `UploadResponse` with per-document character counts

### `routers/documents.py` — GET /api/documents

- Single aggregation query: `GROUP BY document_name`, `SUM(length(chunk_text))`, `COUNT(id)`
- Returns empty list gracefully when no documents exist

### `routers/query.py` — POST /api/query (SSE)

- Fetches all chunks ordered by `id` (insertion order = document upload order)
- Calls `_build_wiki()` to assemble and token-trim the context
- Opens an `httpx.AsyncClient` stream to OpenRouter
- Relays each SSE token as `data: {"token": "..."}` to the client
- Final frame: `data: [DONE]`

---

## 8. API Contracts

### `POST /api/upload`

**Request:** `multipart/form-data`
```
files: UploadFile[]   (one or more files)
```

**Response `200 OK`:**
```json
{
  "documents": [
    {
      "document_name": "report.pdf",
      "total_characters": 42000,
      "chunk_count": 42
    }
  ]
}
```

**Error responses:**

| Code | Condition |
|---|---|
| `400` | No files provided / file yields empty text |
| `413` | File exceeds 10 MB |
| `415` | Unsupported file extension |
| `500` | Parser crash (corrupt file, encoding error) |

---

### `GET /api/documents`

**Response `200 OK`:**
```json
[
  { "document_name": "report.pdf",  "total_characters": 42000, "chunk_count": 42 },
  { "document_name": "data.xlsx",   "total_characters": 8100,  "chunk_count": 9  }
]
```
Returns `[]` when no documents have been uploaded.

**Error responses:**

| Code | Condition |
|---|---|
| `500` | Database error |

---

### `POST /api/query`

**Request:** `application/json`
```json
{ "question": "What is the Q3 revenue?" }
```

**Response:** `text/event-stream` (SSE)
```
data: {"token": "The"}
data: {"token": " Q3"}
data: {"token": " revenue"}
data: {"token": " was"}
data: {"token": " $4.2M."}
data: [DONE]
```

Headers set on response:
```
Cache-Control: no-cache
X-Accel-Buffering: no
```

**Error responses:**

| Code | Condition |
|---|---|
| `400` | Empty question string |
| `400` | No documents uploaded yet |
| `502` | OpenRouter unreachable / API key not set |
| `500` | Internal DB or streaming error |

---

### `GET /health`

```json
{ "status": "ok" }
```

---

## 9. Document Parsing Pipeline

```
User uploads file (binary bytes via multipart)
           │
           ▼
routers/upload.py → content = await upload.read()
           │
           ▼
parsers.extract_and_chunk(filename, content)
           │
           ├─ len(content) > 10 MB?  ──── YES ──► FileTooLargeError  → HTTP 413
           │
           ├─ ext not in ALLOWED?    ──── YES ──► UnsupportedFormatError → HTTP 415
           │
           ▼
_PARSERS[ext](content: bytes) → raw_text: str
           │
           ├── .txt  → content.decode("utf-8", errors="replace")
           │
           ├── .pdf  → fitz.open(stream=content, filetype="pdf")
           │           for page in doc: page.get_text()
           │           join all pages with "\n"
           │
           ├── .docx → docx.Document(BytesIO(content))
           │           for para in doc.paragraphs: para.text
           │           join non-empty paragraphs with "\n"
           │
           ├── .doc  → same as .docx (python-docx handles both)
           │
           ├── .xlsx → openpyxl.load_workbook(BytesIO, read_only=True, data_only=True)
           │           for sheet → for row → cell values → tab-join → row strings
           │           join rows with "\n"
           │
           └── .xls  → xlrd.open_workbook(file_contents=content)
                       for sheet → for rx → cell_value(rx, cx) → tab-join
                       join rows with "\n"
           │
           ▼
_strip_control_chars(raw_text)
           │   regex: [\x00-\x08\x0b\x0c\x0e-\x1f\x7f]
           │   preserves: \n (0x0a), \r (0x0d), \t (0x09)
           ▼
_chunk(cleaned_text, size=1000)
           │   [text[i : i+1000] for i in range(0, len, 1000)
           │    if text[i : i+1000].strip()]   ← skip whitespace-only slices
           ▼
list[str]   e.g. 50 chunks for a 50,000-char document
           │
           ▼
bulk INSERT into document_chunks
  (document_name, chunk_text, chunk_index, uploaded_at)
```

**Example — 20-page PDF:**
```
Raw PDF bytes (2.1 MB)
  → PyMuPDF extracts text: 48,500 chars
  → strip_control_chars: 48,200 chars (300 junk chars removed)
  → _chunk(size=1000): 48 chunks (48×1000 + 1×200)
  → 49 rows inserted into document_chunks
```

---

## 10. Chunking Algorithm

```python
CHUNK_SIZE = 1000  # characters (configurable via settings)

def _chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    cleaned = _strip_control_chars(text)
    return [
        cleaned[i : i + size]
        for i in range(0, len(cleaned), size)
        if cleaned[i : i + size].strip()   # drop whitespace-only chunks
    ]
```

**Properties:**
- Fixed-size, non-overlapping slices
- No sentence boundary detection
- No semantic splitting
- Whitespace-only slices discarded
- Each chunk is at most 1000 characters (last chunk may be shorter)

**Why 1000 chars?**
At ~4 chars/token, 1000 chars ≈ 250 tokens per chunk. With an 8000-token budget, up to ~32 chunks (32,000 chars) fit in one query context. This is approximately 20–25 pages of typical document text.

---

## 11. Wiki Assembly & Token Trimming

At query time, all stored chunks are fetched and assembled into a single string:

```python
CHARS_PER_TOKEN = 4   # conservative estimate

def _build_wiki(chunks: list[str], max_tokens: int = 8000) -> str:
    budget = max_tokens * CHARS_PER_TOKEN   # 32,000 chars
    selected = []
    total = 0
    for chunk in chunks:                    # ordered by id (insertion order)
        if total + len(chunk) > budget:
            break                           # stop — do not truncate mid-chunk
        selected.append(chunk)
        total += len(chunk)
    return "\n\n".join(selected)
```

**Trimming behaviour:**
```
Uploaded docs total:  120,000 chars  (e.g. 3 large PDFs)
Budget:                32,000 chars
Chunks fetched:           120 (ORDER BY id)
Chunks included:           32 (oldest first, stops at budget)
Chunks dropped:            88 (most recently uploaded content)
```

> **Important:** When content exceeds the budget, the **most recently uploaded** documents are dropped first because chunks are ordered by `id` (insertion order). If users want a specific document prioritised, they should upload it last.

---

## 12. LLM Integration (SSE Streaming)

### Request to OpenRouter

```python
payload = {
    "model": settings.openrouter_model,   # "openai/gpt-4o-mini" default
    "stream": True,
    "messages": [
        {
            "role": "system",
            "content": (
                "You are a document assistant. Answer using ONLY "
                "the information in the provided document wiki. "
                "If the answer is not in the wiki, say so clearly.\n\n"
                f"DOCUMENT WIKI:\n{wiki}"
            )
        },
        {"role": "user", "content": question}
    ]
}
```

### SSE Relay Loop

```python
async with httpx.AsyncClient(timeout=60.0) as client:
    async with client.stream("POST", openrouter_url, json=payload) as response:
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data.strip() == "[DONE]":
                break
            token = json.loads(data)["choices"][0]["delta"].get("content", "")
            if token:
                yield f'data: {json.dumps({"token": token})}\n\n'

yield "data: [DONE]\n\n"
```

### Data Flow: OpenRouter → Backend → Client

```
OpenRouter SSE line:
  data: {"id":"...","choices":[{"delta":{"content":"The"}}]}

Backend extracts:
  token = "The"
  yields: data: {"token": "The"}\n\n

Client JS receives:
  EventSource line → JSON.parse → append token to answer string
```

---

## 13. Configuration Reference

All settings read from environment variables or `.env` file via `pydantic-settings`.

| Variable | Default | Type | Description |
|---|---|---|---|
| `DATABASE_URL` | `sqlite:///./noragdocquery.db` | str | SQLAlchemy connection string |
| `OPENROUTER_API_KEY` | `""` | str | **Required** for query endpoint |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | str | OpenRouter API base URL |
| `OPENROUTER_MODEL` | `openai/gpt-4o-mini` | str | Model used for answering queries |
| `MAX_FILE_SIZE_MB` | `10` | int | Per-file upload limit in megabytes |
| `CHUNK_SIZE` | `1000` | int | Characters per text chunk |
| `MAX_CONTEXT_TOKENS` | `8000` | int | Token budget for wiki assembly |

**Example `.env`:**
```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=openai/gpt-4o
MAX_CONTEXT_TOKENS=16000
```

---

## 14. Dependency Graph

```
main.py
  ├── config.py          (no internal deps)
  ├── database.py  ←──── config.py
  ├── models.py    ←──── database.py
  └── routers/
       ├── upload.py    ←── database.py
       │                ←── models.py
       │                ←── schemas.py
       │                ←── parsers.py    (no internal deps)
       │
       ├── documents.py ←── database.py
       │                ←── models.py
       │                ←── schemas.py
       │
       └── query.py     ←── database.py
                        ←── models.py
                        ←── schemas.py
                        ←── config.py
```

`config.py` and `parsers.py` have **zero internal imports** — fully independent, easiest to test in isolation.

---

## 15. Error Handling Matrix

| Location | Exception | HTTP Code | Detail |
|---|---|---|---|
| `upload.py` | `FileTooLargeError` | `413` | `"<filename> exceeds 10 MB limit"` |
| `upload.py` | `UnsupportedFormatError` | `415` | `"Unsupported file type: .<ext>"` |
| `upload.py` | Any parser exception | `500` | `"Parsing failed: <msg>"` |
| `upload.py` | Empty chunk list | `400` | `"<filename>: no text could be extracted"` |
| `upload.py` | No files in request | `400` | `"No files provided"` |
| `documents.py` | DB exception | `500` | Raw exception message |
| `query.py` | Empty question | `400` | `"question must not be empty"` |
| `query.py` | No documents in DB | `400` | `"No documents uploaded yet"` |
| `query.py` | Missing API key | `502` | `"OPENROUTER_API_KEY not configured"` |
| `query.py` | OpenRouter non-200 | `502` | `"OpenRouter error: <body[:200]>"` |

---

## 16. RAG vs noRAGDocQuery

```
RAG Architecture:
  Upload → Embed (embedding model) → Store in Vector DB
  Query  → Embed question → Similarity search → Top-K chunks → LLM

noRAGDocQuery Architecture:
  Upload → Parse → Fixed chunks → Store in SQLite (plain text)
  Query  → SELECT ALL chunks → Assemble wiki → LLM sees everything
```

| Dimension | RAG | noRAGDocQuery |
|---|---|---|
| Chunking strategy | Semantic / sentence-aware / overlapping | Fixed 1000-char non-overlapping slices |
| Storage backend | Vector DB (Chroma, pgvector, FAISS, Pinecone) | SQLite — single `.db` file |
| Retrieval method | Cosine / dot-product similarity on embeddings | `SELECT * FROM document_chunks ORDER BY id` |
| Context sent to LLM | Top-K most semantically relevant chunks | All chunks up to token budget |
| Requires embedding model | Yes (e.g. `text-embedding-ada-002`) | No |
| Relevance accuracy on large docs | High | Degrades past token budget |
| Infrastructure complexity | High | Zero — no additional services |
| Cold start (first upload) | Slow (embedding compute) | Fast (parse + insert only) |
| Best suited for | Large corpora (1000s of docs) | Small–medium docs, local/simple use |

---

## 17. Running Locally

### Prerequisites

```bash
Python 3.9+
pip
```

### Install & Start

```bash
# From the noRAGDocQuery/ parent directory
cd noRAGDocQuery

# Install dependencies
pip install -r backend/requirements.txt

# Create .env
echo "OPENROUTER_API_KEY=sk-or-v1-..." > .env

# Start the server (runs from package root so relative imports resolve)
python -m uvicorn backend.main:app --reload --port 8000
```

### Verify

```bash
curl http://localhost:8000/health
# → {"status":"ok"}

curl http://localhost:8000/docs
# → FastAPI Swagger UI
```

### Run Migrations (production)

```bash
cd backend
alembic upgrade head
```

---

## 18. Testing

```bash
# From noRAGDocQuery/ parent directory
python -m pytest backend/tests/ -v
```

**Test coverage:**

| Test | File | What it verifies |
|---|---|---|
| `test_upload_txt_success` | `test_upload.py` | TXT file → 200, correct doc summary |
| `test_upload_unsupported_extension` | `test_upload.py` | `.exe` → 415 |
| `test_upload_too_large` | `test_upload.py` | 11 MB file → 413 |
| `test_documents_list_empty` | `test_upload.py` | Empty DB → `[]` |
| `test_documents_list_after_upload` | `test_upload.py` | Upload then list → doc appears |

Each test uses an **in-memory SQLite test database** spun up fresh per test via `autouse` fixture — no shared state between tests.
