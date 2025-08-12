# src/sensory_data_client/db/document_image_orm.py

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    String, DateTime, Text, Integer, ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

class DocumentImageORM(Base):
    """
    Таблица для отслеживания статуса обработки изображений из документов.
    """
    __tablename__ = "document_images"
    __table_args__ = (
        UniqueConstraint("document_id", "image_hash", name="uq_document_image_hash"),
        Index("ix_document_images_status", "status"),
        Index("ix_document_images_doc_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.uuid_generate_v4(),
        default=uuid4
    )
    # Связи
    document_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    source_line_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("document_lines.id", ondelete="SET NULL"), nullable=True, index=True)

    # Местоположение и идентификация
    object_key: Mapped[str] = mapped_column(String, nullable=False, unique=True) # например: "pdf/1363.../images/0c18...png"
    filename: Mapped[str] = mapped_column(String, nullable=False)
    image_hash: Mapped[str] = mapped_column(String, nullable=False) # "0c18...": имя без расширения, для дедупликации

    # Статус обработки
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending") # pending | enqueued | processing | done | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Результат от LLM
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document = relationship("DocumentORM")
    source_line = relationship("DocumentLineORM")