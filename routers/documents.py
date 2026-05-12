from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Annotated

from ..database import get_db
from ..models import DocumentChunk
from ..schemas import DocumentSummary

router = APIRouter(prefix="/api", tags=["documents"])


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
