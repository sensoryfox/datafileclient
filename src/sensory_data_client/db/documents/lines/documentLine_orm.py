# sensory_data_client/db/documentLine_orm.py
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, func, Index, Integer
from typing import List, Optional
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Double
from sensory_data_client.db.base import Base, UpdatedAt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensory_data_client.db.documents.lines.rawline_orm import RawLineORM
    from sensory_data_client.db import DocumentORM

class DocumentLineORM(Base):
    __tablename__ = "lines_document"
    line_id: Mapped[UUID] = mapped_column(ForeignKey("raw_lines.id", ondelete="CASCADE"), primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    # --- Ключевые поля, соответствующие Pydantic-модели ---
    page_idx: Mapped[int] = mapped_column(Integer, nullable=True)   # Номер страницы
    block_id: Mapped[str] = mapped_column(String, nullable=True)    # ID блока из парсера  
    # --- Хранение геометрии и метаданных ---
    # JSONB - бинарный, индексируемый JSON, идеален для этого
    geometry: Mapped[dict] = mapped_column(JSONB, nullable=True) # Хранит { "polygon": [...], "bbox": [...] }
    hierarchy: Mapped[dict] = mapped_column(JSONB, nullable=True)# Хранит { "polygon": [...], "bbox": [...] }
    attrs: Mapped[dict] = mapped_column(JSONB, nullable=True) # Хранит атрибуты
    
    #document = relationship(back_populates="details_document")
    line = relationship("RawLineORM", back_populates="document_details")
    document: Mapped["DocumentORM"] = relationship(
        "DocumentORM",
        back_populates="document_lines" # Указываем точное имя обратной связи из DocumentORM
    )
    # --- Связи ---

    __table_args__ = (
        Index("idx_lines_document_doc_id", "doc_id"),
        Index("idx_lines_document_page_idx", "page_idx"),
        Index("idx_lines_document_block_id", "block_id"),
    )