"""Document upload, parsing, chunking, and retrieval endpoints."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..document_models import Base, DocumentChunk
from ..schemas.documents import ChunkSummary, DocumentListItem, DocumentListResponse, DocumentUploadResponse
from ..services.parser import SUPPORTED_EXTENSIONS, parse_and_chunk

_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./norag.db")
_engine = create_async_engine(_DATABASE_URL, echo=False, future=True)
_SessionLocal = async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _sanitize(text: str) -> str:
    return _CONTROL_CHAR_RE.sub("", text)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)) -> DocumentUploadResponse:
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE // (1024 * 1024)} MB limit.",
        )

    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")

    document_name = file.filename or "upload"
    raw_chunks = parse_and_chunk(data, document_name)
    chunks = [_sanitize(c) for c in raw_chunks]

    chunk_records = [
        DocumentChunk(
            document_name=document_name,
            content=chunk,
            chunk_index=i,
        )
        for i, chunk in enumerate(chunks)
    ]

    async with _SessionLocal() as session:
        async with session.begin():
            session.add_all(chunk_records)

    return DocumentUploadResponse(
        document_name=document_name,
        chunk_count=len(chunks),
        total_characters=sum(len(c) for c in chunks),
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents() -> DocumentListResponse:
    async with _SessionLocal() as session:
        result = await session.execute(
            select(
                DocumentChunk.document_name,
                func.count(DocumentChunk.id).label("chunk_count"),
                func.sum(func.length(DocumentChunk.content)).label("total_characters"),
            ).group_by(DocumentChunk.document_name)
        )
        rows = result.all()

    items = [
        DocumentListItem(
            name=row.document_name,
            chunk_count=row.chunk_count,
            total_characters=row.total_characters or 0,
        )
        for row in rows
    ]
    return DocumentListResponse(documents=items, total=len(items))


@router.get("/{document_name}/chunks", response_model=List[ChunkSummary])
async def list_chunk_summaries(document_name: str) -> list[ChunkSummary]:
    async with _SessionLocal() as session:
        result = await session.execute(
            select(DocumentChunk.chunk_index, func.length(DocumentChunk.content).label("char_count"))
            .where(DocumentChunk.document_name == document_name)
            .order_by(DocumentChunk.chunk_index)
        )
        rows = result.all()

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    return [ChunkSummary(chunk_index=r.chunk_index, char_count=r.char_count) for r in rows]
