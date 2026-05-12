from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Annotated, AsyncIterator
import httpx
import json

from ..database import get_db
from ..models import KnowledgeBase
from ..schemas import QueryRequest
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["query"])


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

    kb = db.get(KnowledgeBase, 1)
    if kb is None:
        raise HTTPException(
            status_code=400,
            detail="Knowledge base not built yet. Upload documents and click 'Update Knowledge Base' first.",
        )

    return StreamingResponse(
        _stream_openrouter(kb.wiki_text, body.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
