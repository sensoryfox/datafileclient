from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, Text
from sqlalchemy import String, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base

class DocumentLineORM(Base):
    __tablename__ = "document_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    line_no: Mapped[int] = mapped_column(nullable=False)
    
    # Структурные метаданные
    page_idx: Mapped[int] = mapped_column(nullable=True)
    sheet_name: Mapped[str] = mapped_column(String(255), nullable=True)
    block_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True) # paragraph, image, table, h1, etc.
    block_id: Mapped[str] = mapped_column(String(255), nullable=True) # ID из парсера (если есть)

    # Контент
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Временные метки
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("document_id", "line_no", name="uq_document_line_no"),
        # Индекс для полнотекстового поиска по строкам
        Index("ix_document_lines_content_fts", func.to_tsvector('simple', content), postgresql_using='gin'),
    )