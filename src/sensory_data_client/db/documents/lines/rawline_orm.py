from __future__ import annotations
from uuid import UUID, uuid4
from sqlalchemy import String, Text, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sensory_data_client.db.base import Base, CreatedAt, UpdatedAt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sensory_data_client.db.documents.document_orm import DocumentORM
    from sensory_data_client.db.documents.lines.documentLine_orm import DocumentLineORM
    from sensory_data_client.db.documents.lines.imageLine_orm import ImageLineORM
    from sensory_data_client.db.documents.lines.audioLine_orm import AudioLineORM

class RawLineORM(Base):
    __tablename__ = "raw_lines"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), 
                                         ForeignKey("documents.id", ondelete="CASCADE"), 
                                         nullable=False)
    
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    block_type: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default='') # Текст, транскрипт, alt-text
    created_at: Mapped[CreatedAt]
    update_at: Mapped[UpdatedAt]


    # Связи "один-к-одному" с таблицами деталей
    document = relationship("DocumentORM", back_populates="raw_lines")
    document_details = relationship("DocumentLineORM", back_populates="line", uselist=False, cascade="all, delete-orphan")
    image_details = relationship("ImageLineORM", back_populates="line", uselist=False, cascade="all, delete-orphan")
    audio_details = relationship("AudioLineORM", back_populates="line", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_raw_lines_doc_id", "doc_id"),
        Index("idx_raw_lines_doc_id_position", "doc_id", "position"),
    )