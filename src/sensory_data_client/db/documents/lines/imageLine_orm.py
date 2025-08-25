# src/sensory_data_client/db/document_image_orm.py

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    String, DateTime, Text, Integer, ForeignKey, UniqueConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base

class ImageLineORM(Base):
    """
    Таблица для отслеживания статуса обработки изображений из документов.
    """
    __tablename__ = "lines_image"

    line_id: Mapped[UUID] = mapped_column(ForeignKey("raw_lines.id", ondelete="CASCADE"), primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    # Местоположение и идентификация
    filename: Mapped[str] = mapped_column(String, nullable=False)
    image_hash: Mapped[str] = mapped_column(String, nullable=False) # "0c18...": имя без расширения, для дедупликации
    # Статус обработки
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending") # pending | enqueued | processing | done | failed
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Результат от LLM                 # Итоговое описание (LLM) 
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)  
    llm_model: Mapped[str | None] = mapped_column(String, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Временные метки
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    line = relationship("RawLineORM", back_populates="image_details")
    document: Mapped["DocumentORM"] = relationship(
        "DocumentORM",
        back_populates="image_lines" # Указываем точное имя обратной связи из DocumentORM
    )
    
__table_args__ = (
        Index("idx_lines_image_doc_id", "doc_id"),
        Index("idx_lines_image_image_hash", "image_hash"),
        Index("idx_lines_image_updated_at", "updated_at"),
    )