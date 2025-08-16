# sensory_data_client/db/documentLine_orm.py
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, func, Index, Integer

from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Double
from sensory_data_client.db.base import Base

class DocumentLineORM(Base):
    __tablename__ = "document_lines"
    id:          Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True),
                                              primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    
    # --- Ключевые поля, соответствующие Pydantic-модели ---
    position: Mapped[int] = mapped_column(Integer, nullable=False) # Порядковый номер строки
    page_idx: Mapped[int] = mapped_column(Integer, nullable=True)   # Номер страницы
    
    block_id: Mapped[str] = mapped_column(String, nullable=True)    # ID блока из парсера
    block_type: Mapped[str] = mapped_column(String, nullable=True)  # Тип блока (Text, TableCell, etc)
    
    content: Mapped[str] = mapped_column(Text, nullable=False)      # Текстовое содержимое
    
    # --- Хранение геометрии и метаданных ---
    # JSONB - бинарный, индексируемый JSON, идеален для этого
    geometry: Mapped[dict] = mapped_column(JSONB, nullable=True) # Хранит { "polygon": [...], "bbox": [...] }
    hierarchy: Mapped[dict] = mapped_column(JSONB, nullable=True) # Хранит section_hierarchy
    sheet_name: Mapped[str] = mapped_column(String, nullable=True)
    # --- Системные поля ---
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped["DocumentORM"] = relationship("DocumentORM", back_populates="lines")
    images: Mapped[list["DocumentImageORM"]] = relationship("DocumentImageORM", back_populates="source_line")
    

    # --- Связи ---
    __table_args__ = (
        Index("idx_document_lines_doc_id_position", "doc_id", "position"),
    )