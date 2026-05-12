from pydantic import BaseModel
from datetime import datetime


class DocumentSummary(BaseModel):
    document_name: str
    total_characters: int
    chunk_count: int


class UploadResponse(BaseModel):
    documents: list[DocumentSummary]


class QueryRequest(BaseModel):
    question: str


class DocumentChunkSchema(BaseModel):
    id: int
    document_name: str
    chunk_index: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class DocumentPreview(BaseModel):
    document_name: str
    content: str
    chunk_count: int


class ContextResponse(BaseModel):
    content: str
    total_characters: int
    document_count: int
