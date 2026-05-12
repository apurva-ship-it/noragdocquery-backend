from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Annotated, AsyncIterator
import httpx
import json

from ..database import get_db
from ..models import DocumentChunk
from ..schemas import QueryRequest
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["query"])

CHARS_PER_TOKEN = 4  # rough estimate: 1 token ≈ 4 chars


def _build_wiki(chunks: list[str], max_tokens: int) -> str:
    """Concatenate chunks in order, dropping oldest when over token budget."""
    budget = max_tokens * CHARS_PER_TOKEN
    selected: list[str] = []
    total = 0
    for chunk in chunks:
        if total + len(chunk) > budget:
            break
        selected.append(chunk)
        total += len(chunk)
    return "\n\n".join(selected)


async def _stream_openrouter(wiki: str, question: str) -> AsyncIterator[str]:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=502, detail="OPENROUTER_API_KEY not configured")

    payload = {
        "model": settings.openrouter_model,
        "stream": True,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a document assistant. Answer the user's question using ONLY "
                    "the information in the provided document wiki. If the answer is not "
                    "in the wiki, say so clearly.\n\n"
                    f"DOCUMENT WIKI:\n{wiki}"
                ),
            },
            {"role": "user", "content": question},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/noRAGDocQuery",
        "X-Title": "noRAGDocQuery",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream(
            "POST",
            f"{settings.openrouter_base_url}/chat/completions",
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise HTTPException(status_code=502, detail=f"OpenRouter error: {body.decode()[:200]}")

            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield f"data: {json.dumps({'token': delta})}\n\n"
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    yield "data: [DONE]\n\n"


@router.post("/query")
async def query_documents(
    body: QueryRequest,
    db: Annotated[Session, Depends(get_db)],
) -> StreamingResponse:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    settings = get_settings()

    chunks = db.execute(
        select(DocumentChunk.chunk_text).order_by(DocumentChunk.id)
    ).scalars().all()

    if not chunks:
        raise HTTPException(status_code=400, detail="No documents uploaded yet")

    wiki = _build_wiki(list(chunks), settings.max_context_tokens)

    return StreamingResponse(
        _stream_openrouter(wiki, body.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
