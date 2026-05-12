"""Pydantic schemas for the documents API."""
from typing import List

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    document_name: str
    chunk_count: int
    total_characters: int

    model_config = {"from_attributes": True}


class DocumentListItem(BaseModel):
    name: str
    chunk_count: int
    total_characters: int


class DocumentListResponse(BaseModel):
    documents: List[DocumentListItem]
    total: int


class ChunkSummary(BaseModel):
    chunk_index: int
    char_count: int
