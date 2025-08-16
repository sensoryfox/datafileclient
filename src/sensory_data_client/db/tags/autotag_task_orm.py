# sensory_data_client/db/tags/autotag_task_orm.py

from __future__ import annotations
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import String, Text, Integer, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, CreatedAt, UpdatedAt

class AutotagTaskORM(Base):
    __tablename__ = "autotag_tasks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    
    # Статус задачи: 'enqueued', 'processing', 'done', 'failed'.
    status: Mapped[str] = mapped_column(String(50), default="enqueued", nullable=False)
    
    # Количество попыток обработки.
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Результат работы модели (например, список найденных тегов).
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # Текст последней ошибки для отладки.
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    
    # Имя модели, которая использовалась для генерации тегов.
    llm_model: Mapped[str] = mapped_column(String(255), nullable=True)

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
    processed_at: Mapped[datetime] = mapped_column(nullable=True)
    
    __table_args__ = (
        Index("idx_autotag_tasks_status", "status"),
        Index("idx_autotag_tasks_doc_id", "doc_id"),
    )