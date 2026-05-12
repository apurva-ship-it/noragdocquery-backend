"""Integration tests for the GET /api/documents list endpoint."""
from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.document_models import Base, DocumentChunk
from backend.main import app
import backend.routers.documents as docs_router


# ---------------------------------------------------------------------------
# In-memory SQLite engine used only during tests
# ---------------------------------------------------------------------------

_TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_test_engine = create_async_engine(_TEST_DATABASE_URL, echo=False, future=True)
_TestSession = async_sessionmaker(bind=_test_engine, expire_on_commit=False, class_=AsyncSession)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and drop them after."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    original = docs_router._SessionLocal
    docs_router._SessionLocal = _TestSession
    yield
    docs_router._SessionLocal = original
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        yield ac


async def _seed(chunks: list[tuple[str, int, str]]) -> None:
    """Insert (document_name, chunk_index, content) rows into the test DB."""
    async with _TestSession() as session:
        async with session.begin():
            session.add_all(
                [DocumentChunk(document_name=name, chunk_index=idx, content=content)
                 for name, idx, content in chunks]
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_documents_empty_db_returns_200_with_empty_list(client):
    resp = await client.get("/api/documents")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["documents"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_single_document(client):
    await _seed([("report.txt", 0, "hello"), ("report.txt", 1, "world")])
    resp = await client.get("/api/documents")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 1
    doc = body["documents"][0]
    assert doc["name"] == "report.txt"
    assert doc["chunk_count"] == 2
    assert doc["total_characters"] == len("hello") + len("world")


@pytest.mark.asyncio
async def test_list_documents_multiple_documents(client):
    await _seed([
        ("a.txt", 0, "aaa"),
        ("b.txt", 0, "bb"),
        ("b.txt", 1, "b"),
    ])
    resp = await client.get("/api/documents")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 2
    by_name = {d["name"]: d for d in body["documents"]}
    assert by_name["a.txt"]["chunk_count"] == 1
    assert by_name["a.txt"]["total_characters"] == 3
    assert by_name["b.txt"]["chunk_count"] == 2
    assert by_name["b.txt"]["total_characters"] == 3


@pytest.mark.asyncio
async def test_list_documents_response_shape(client):
    await _seed([("doc.txt", 0, "x" * 100)])
    resp = await client.get("/api/documents")
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert "documents" in body
    assert "total" in body
    item = body["documents"][0]
    assert set(item.keys()) == {"name", "chunk_count", "total_characters"}
