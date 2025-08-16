# sensory_data_client/db/tags/document_tag_orm.py

from __future__ import annotations
from uuid import UUID
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sensory_data_client.db.base import Base

class DocumentTagORM(Base):
    __tablename__ = "document_tags"

    # Составной первичный ключ гарантирует уникальность пары (документ, тег).
    doc_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[UUID] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)

    # Источник тега: 'manual' (добавлен пользователем) или 'auto' (сгенерирован моделью).
    # Это ключевое поле для фильтрации и управления тегами.
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)