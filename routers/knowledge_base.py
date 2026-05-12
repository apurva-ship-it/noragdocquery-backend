from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete
from typing import Annotated, Optional
from datetime import datetime, timezone
import json

from ..database import get_db
from ..models import DocumentChunk, KnowledgeBase
from ..schemas import KnowledgeBaseStatus
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["knowledge-base"])

CHARS_PER_TOKEN = 4


def _current_doc_names(db: Session) -> list[str]:
    rows = db.execute(
        select(DocumentChunk.document_name).distinct()
    ).scalars().all()
    return sorted(rows)


def _get_kb(db: Session) -> Optional[KnowledgeBase]:
    return db.get(KnowledgeBase, 1)


def _is_stale(kb: Optional[KnowledgeBase], current_names: list[str]) -> bool:
    if kb is None:
        return True
    return set(kb.document_names) != set(current_names)


@router.get("/knowledge-base/status", response_model=KnowledgeBaseStatus)
def get_kb_status(db: Annotated[Session, Depends(get_db)]) -> KnowledgeBaseStatus:
    kb = _get_kb(db)
    current_names = _current_doc_names(db)
    return KnowledgeBaseStatus(
        has_kb=kb is not None,
        is_stale=_is_stale(kb, current_names),
        updated_at=kb.updated_at if kb else None,
        total_characters=kb.total_characters if kb else 0,
        document_count=len(kb.document_names) if kb else 0,
        document_names=kb.document_names if kb else [],
    )


@router.post("/knowledge-base", response_model=KnowledgeBaseStatus)
def build_knowledge_base(db: Annotated[Session, Depends(get_db)]) -> KnowledgeBaseStatus:
    settings = get_settings()
    budget = settings.max_context_tokens * CHARS_PER_TOKEN

    chunks = db.execute(
        select(DocumentChunk.chunk_text).order_by(DocumentChunk.id)
    ).scalars().all()

    if not chunks:
        raise HTTPException(status_code=400, detail="No documents uploaded. Upload files first.")

    selected: list[str] = []
    total = 0
    for chunk in chunks:
        if total + len(chunk) > budget:
            break
        selected.append(chunk)
        total += len(chunk)

    wiki_text = "\n\n".join(selected)
    current_names = _current_doc_names(db)
    now = datetime.now(timezone.utc)

    # Upsert — always keep exactly one row (id=1)
    db.execute(delete(KnowledgeBase))
    kb = KnowledgeBase(
        id=1,
        wiki_text=wiki_text,
        document_names_json=json.dumps(current_names),
        total_characters=total,
        updated_at=now,
    )
    db.add(kb)
    db.commit()

    return KnowledgeBaseStatus(
        has_kb=True,
        is_stale=False,
        updated_at=now,
        total_characters=total,
        document_count=len(current_names),
        document_names=current_names,
    )
