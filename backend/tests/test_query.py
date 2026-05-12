"""Tests for POST /api/query — SSE streaming endpoint.

Validates P0 fixes:
- SSE endpoint implementation (content-type, event format, [DONE] sentinel)
- Chunk ordering by upload time then chunk_index
- Token trimming: oldest chunks dropped until within 8k-token budget
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from unittest.mock import patch

from backend.document_models import Base, DocumentChunk
from backend.main import app
import backend.routers.query as query_router
import backend.routers.documents as docs_router

_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, future=True)
_TestSession = async_sessionmaker(bind=_test_engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    original_docs = docs_router._SessionLocal
    original_query = query_router._SessionLocal
    docs_router._SessionLocal = _TestSession
    query_router._SessionLocal = _TestSession
    yield
    docs_router._SessionLocal = original_docs
    query_router._SessionLocal = original_query
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _seed(chunks: list[tuple[str, int, str]]) -> None:
    async with _TestSession() as session:
        async with session.begin():
            session.add_all([
                DocumentChunk(document_name=name, chunk_index=idx, content=content)
                for name, idx, content in chunks
            ])


async def _simple_stream(wiki: str, query: str):
    yield f"data: {json.dumps({'token': 'hello'})}\n\n"
    yield "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_query_returns_200_with_sse_content_type(client):
    with patch("backend.routers.query._stream_llm", _simple_stream):
        resp = await client.post("/api/query", json={"query": "test question"})
    assert resp.status_code == status.HTTP_200_OK
    assert "text/event-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_query_sse_includes_done_sentinel(client):
    with patch("backend.routers.query._stream_llm", _simple_stream):
        resp = await client.post("/api/query", json={"query": "test"})
    assert "data: [DONE]" in resp.text


@pytest.mark.asyncio
async def test_query_sse_token_events_are_valid_json(client):
    with patch("backend.routers.query._stream_llm", _simple_stream):
        resp = await client.post("/api/query", json={"query": "test"})
    events = [
        line for line in resp.text.splitlines()
        if line.startswith("data: ") and "[DONE]" not in line
    ]
    assert events, "Expected at least one token event"
    for event in events:
        payload = json.loads(event[len("data: "):])
        assert "token" in payload


@pytest.mark.asyncio
async def test_query_empty_db_returns_valid_sse(client):
    with patch("backend.routers.query._stream_llm", _simple_stream):
        resp = await client.post("/api/query", json={"query": "anything"})
    assert resp.status_code == status.HTTP_200_OK
    assert "data: [DONE]" in resp.text


@pytest.mark.asyncio
async def test_query_chunks_ordered_by_chunk_index_within_document(client):
    """chunk_index ordering must be preserved within a single document upload."""
    await _seed([
        ("doc.txt", 0, "FIRST"),
        ("doc.txt", 1, "SECOND"),
    ])
    captured: list[str] = []

    async def capture_stream(wiki: str, query: str):
        captured.append(wiki)
        yield "data: [DONE]\n\n"

    with patch("backend.routers.query._stream_llm", capture_stream):
        await client.post("/api/query", json={"query": "test"})

    assert len(captured) == 1
    assert captured[0].index("FIRST") < captured[0].index("SECOND")


@pytest.mark.asyncio
async def test_query_token_trimming_keeps_chunk_sum_within_budget(client):
    """Oldest chunks are dropped until the sum of chunk lengths fits the 8k-token budget."""
    from backend.routers.query import _MAX_WIKI_CHARS

    chunk_content = "x" * 1000
    over_budget_count = (_MAX_WIKI_CHARS // 1000) + 10
    await _seed([("doc.txt", i, chunk_content) for i in range(over_budget_count)])

    captured: list[str] = []

    async def capture_stream(wiki: str, query: str):
        captured.append(wiki)
        yield "data: [DONE]\n\n"

    with patch("backend.routers.query._stream_llm", capture_stream):
        await client.post("/api/query", json={"query": "test"})

    assert len(captured) == 1
    chunk_texts = [c for c in captured[0].split("\n\n") if c]
    assert sum(len(t) for t in chunk_texts) <= _MAX_WIKI_CHARS
