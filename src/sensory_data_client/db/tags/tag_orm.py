# sensory_data_client/db/tags/tag_orm.py

from __future__ import annotations
from uuid import UUID, uuid4
from typing import List, Optional 
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sensory_data_client.db.base import Base, CreatedAt
from typing import TYPE_CHECKING
from pgvector.sqlalchemy import VECTOR

if TYPE_CHECKING:
    from sensory_data_client.db.documents.document_orm import DocumentORM

class TagORM(Base):
    __tablename__ = "tags"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Имя тега. Должно быть уникальным, чтобы не было дублей "Python" и "python".
    # Нормализация (например, приведение к нижнему регистру) - задача репозитория.
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    vector: Mapped[Optional[List[float]]] = mapped_column(VECTOR(1024), nullable=True)
    
    created_at: Mapped[CreatedAt]

    # Связь многие-ко-многим с документами.
    documents: Mapped[List["DocumentORM"]] = relationship(
        secondary="document_tags", back_populates="tags", lazy="selectin"
    )