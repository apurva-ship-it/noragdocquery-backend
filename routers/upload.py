from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from typing import Annotated
from datetime import datetime, timezone

from ..database import get_db
from ..models import DocumentChunk
from ..schemas import UploadResponse, DocumentSummary
from ..parsers import extract_and_chunk, UnsupportedFormatError, FileTooLargeError

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadResponse)
async def upload_files(
    files: Annotated[list[UploadFile], File(...)],
    db: Annotated[Session, Depends(get_db)],
) -> UploadResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    summaries: list[DocumentSummary] = []

    for upload in files:
        filename = upload.filename or "unknown"
        content = await upload.read()

        try:
            chunks = extract_and_chunk(filename, content)
        except FileTooLargeError as e:
            raise HTTPException(status_code=413, detail=str(e))
        except UnsupportedFormatError as e:
            raise HTTPException(status_code=415, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Parsing failed: {e}")

        if not chunks:
            raise HTTPException(status_code=400, detail=f"{filename}: no text could be extracted")

        now = datetime.now(timezone.utc)
        db_chunks = [
            DocumentChunk(
                document_name=filename,
                chunk_text=chunk,
                chunk_index=idx,
                uploaded_at=now,
            )
            for idx, chunk in enumerate(chunks)
        ]
        db.bulk_save_objects(db_chunks)
        db.commit()

        total_chars = sum(len(c) for c in chunks)
        summaries.append(
            DocumentSummary(
                document_name=filename,
                total_characters=total_chars,
                chunk_count=len(chunks),
            )
        )

    return UploadResponse(documents=summaries)
