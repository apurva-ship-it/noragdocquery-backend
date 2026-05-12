from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from .database import Base
import json


class KnowledgeBase(Base):
    """Persisted wiki snapshot. Always at most one row (id=1, upserted on rebuild)."""
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    wiki_text: Mapped[str] = mapped_column(Text, nullable=False)
    document_names_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    total_characters: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    @property
    def document_names(self) -> list[str]:
        return json.loads(self.document_names_json)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
