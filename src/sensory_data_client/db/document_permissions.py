# sensory_data_client/db/document_permissions.py
from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey, Integer, UniqueConstraint
from typing import List, Optional

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base

class DocumentPermissionORM(Base):
    __tablename__ = "document_permissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    
    # Разрешение может быть дано либо пользователю, либо группе
    user_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("users.id"), index=True)
    group_id: Mapped[Optional[UUID]] = mapped_column(ForeignKey("groups.id"), index=True)
    
    # Уровень доступа: 'view', 'edit', 'owner'
    permission_level: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (UniqueConstraint('doc_id', 'user_id', 'permission_level'),
                      UniqueConstraint('doc_id', 'group_id', 'permission_level'))