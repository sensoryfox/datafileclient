from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Index, Text
from sqlalchemy import String, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base
from ..models.document import DocumentInDB


class DocumentORM(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("owner", "user_document_id", name="uq_owner_user_document_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_document_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    access_group: Mapped[str | None] = mapped_column(String, nullable=True)
    extension: Mapped[str | None] = mapped_column(String, nullable=True)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    object_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    md_object_path: Mapped[str | None] = mapped_column(String, unique=True)
    metadata_: Mapped[dict | None] = mapped_column(JSONB)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    edited: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_pydantic(self) -> DocumentInDB:
        return DocumentInDB(
            id=self.id,
            user_document_id=self.user_document_id,
            name=self.name,
            owner=self.owner,
            access_group=self.access_group,
            extension=self.extension,
            content_hash=self.content_hash,
            metadata=self.metadata_,
            object_path=self.object_path,
            md_object_path=self.md_object_path,
            created=self.created,
            edited=self.edited,
        )

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