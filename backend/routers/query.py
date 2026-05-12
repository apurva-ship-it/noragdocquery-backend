"""POST /api/query — builds wiki from document chunks, streams LLM response via SSE."""
from __future__ import annotations

import asyncio
import json
import os

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from ..document_models import DocumentChunk
from .documents import _SessionLocal

router = APIRouter(prefix="/api", tags=["query"])

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3-haiku")
_MAX_WIKI_TOKENS = 8000
_CHARS_PER_TOKEN = 4
_MAX_WIKI_CHARS = _MAX_WIKI_TOKENS * _CHARS_PER_TOKEN  # 32 000


class QueryRequest(BaseModel):
    query: str


async def _stream_llm(wiki: str, query: str):
    """Async generator yielding SSE-formatted lines from OpenRouter with up to 2 retries."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    payload = {
        "model": _MODEL,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Answer the user's question using only the reference material below.\n\n"
                    f"{wiki}"
                ),
            },
            {"role": "user", "content": query},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "noRAGDocQuery",
    }

    last_exc: str = ""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
                async with client.stream("POST", _OPENROUTER_URL, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            chunk = json.loads(data)
                            token = chunk["choices"][0]["delta"].get("content") or ""
                            if token:
                                yield f"data: {json.dumps({'token': token})}\n\n"
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
            yield "data: [DONE]\n\n"
            return
        except httpx.HTTPStatusError as exc:
            last_exc = f"upstream error {exc.response.status_code}"
        except Exception as exc:
            last_exc = str(exc)

        if attempt < 2:
            await asyncio.sleep(2**attempt)

    yield f"data: {json.dumps({'error': last_exc})}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/query")
async def query_documents(request: QueryRequest) -> StreamingResponse:
    async with _SessionLocal() as session:
        result = await session.execute(
            select(DocumentChunk).order_by(DocumentChunk.created_at, DocumentChunk.chunk_index)
        )
        chunks = result.scalars().all()

    # Concatenate in upload order; drop oldest chunks until within the 8k-token budget
    chunk_texts = [c.content for c in chunks]
    while chunk_texts and sum(len(t) for t in chunk_texts) > _MAX_WIKI_CHARS:
        chunk_texts.pop(0)

    wiki = "\n\n".join(chunk_texts)

    return StreamingResponse(
        _stream_llm(wiki, request.query),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
