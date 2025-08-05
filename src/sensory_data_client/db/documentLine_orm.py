# sensory_data_client/db/documentLine_orm.py
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, func, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Double
from sensory_data_client.db.base import Base

from sensory_data_client.db.base import Base
class DocumentLineORM(Base):
    """
    Каждая строка markdown-/plain-документа.
    """
    __tablename__ = "document_lines"
    __table_args__ = (
        UniqueConstraint("document_id", "position", name="uq_doc_pos"),
        Index("ix_doc_id", "document_id"),
    )

    id:          Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True),
                                              primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    # block_id используется, например, для <img id="...">
    block_id:    Mapped[str  | None] = mapped_column(String, nullable=True)
    position: Mapped[float] = mapped_column(Double, nullable=False) #      # № строки
    type:        Mapped[str] = mapped_column(String, nullable=False)  # md / txt / …
    content:     Mapped[str] = mapped_column(Text,   nullable=False)

    created:     Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # ––– «бедная» (без вложенных объектов) связь «много-к-одному»
    document = relationship("DocumentORM", back_populates="lines")