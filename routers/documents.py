from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete
from typing import Annotated

from ..database import get_db
from ..models import DocumentChunk
from ..schemas import DocumentSummary, DocumentPreview, ContextResponse
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["documents"])

CHARS_PER_TOKEN = 4


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentSummary]:
    try:
        rows = db.execute(
            select(
                DocumentChunk.document_name,
                func.sum(func.length(DocumentChunk.chunk_text)).label("total_characters"),
                func.count(DocumentChunk.id).label("chunk_count"),
            ).group_by(DocumentChunk.document_name)
        ).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return [
        DocumentSummary(
            document_name=row.document_name,
            total_characters=row.total_characters or 0,
            chunk_count=row.chunk_count,
        )
        for row in rows
    ]


@router.delete("/documents/{document_name}", status_code=204)
def delete_document(
    document_name: str,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    result = db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_name == document_name)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found")
    db.commit()


@router.get("/documents/{document_name}/preview", response_model=DocumentPreview)
def preview_document(
    document_name: str,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentPreview:
    chunks = db.execute(
        select(DocumentChunk.chunk_text)
        .where(DocumentChunk.document_name == document_name)
        .order_by(DocumentChunk.chunk_index)
    ).scalars().all()

    if not chunks:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found")

    return DocumentPreview(
        document_name=document_name,
        content="\n\n".join(chunks),
        chunk_count=len(chunks),
    )


@router.get("/context", response_model=ContextResponse)
def get_context(
    db: Annotated[Session, Depends(get_db)],
) -> ContextResponse:
    settings = get_settings()
    budget = settings.max_context_tokens * CHARS_PER_TOKEN

    chunks = db.execute(
        select(DocumentChunk.chunk_text, DocumentChunk.document_name).order_by(DocumentChunk.id)
    ).all()

    if not chunks:
        return ContextResponse(content="", total_characters=0, document_count=0)

    selected: list[str] = []
    total = 0
    for row in chunks:
        if total + len(row.chunk_text) > budget:
            break
        selected.append(row.chunk_text)
        total += len(row.chunk_text)

    doc_names = db.execute(
        select(func.count(func.distinct(DocumentChunk.document_name)))
    ).scalar() or 0

    return ContextResponse(
        content="\n\n".join(selected),
        total_characters=total,
        document_count=int(doc_names),
    )
