from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy import Index, Boolean
from sqlalchemy import String, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from sensory_data_client.db.base import Base
from sensory_data_client.models.document import DocumentInDB
from .document_permissions import DocumentPermissionORM

class DocumentORM(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("owner_id", "user_document_id", name="uq_owner_user_document_id"),
    )

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4) # ID на стороне сервера
    user_document_id: Mapped[str] = mapped_column(String, nullable=False) # ID на стороне клиента
    stored_file_id: Mapped[int] = mapped_column(
        ForeignKey("stored_files.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    
    name: Mapped[str] = mapped_column(String, nullable=False)
    
    # 'PRIVATE' - только владелец
    # 'GROUP' - доступ у группы, указанной в 'access_group_id'
    # 'SHARED' - доступ у явно перечисленных пользователей/групп в `permissions`
    # 'PUBLIC' - доступен всем аутентифицированным пользователям
    owner_id: Mapped[UUID] = mapped_column(PG_UUID, ForeignKey("users.id"), nullable=False, index=True)
    access_group_id: Mapped[Optional[UUID]] = mapped_column(PG_UUID, ForeignKey("groups.id"), index=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONB)
    
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    edited: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    permissions = relationship(
        "DocumentPermissionORM", 
        back_populates="document",
        cascade="all, delete-orphan"
    )
    owner = relationship("UserORM")
    access_group = relationship("GroupORM")
    stored_file = relationship("StoredFileORM", lazy="joined")
    lines = relationship("DocumentLineORM", back_populates="document",
                         cascade="all, delete-orphan")
    
    def to_pydantic(self) -> DocumentInDB:
        """
        Конвертирует ORM-объект в Pydantic-модель DocumentInDB.
        Берет поля content_hash и object_path из связанного объекта stored_file.
        """
        if not self.stored_file:
            raise ValueError("Cannot convert to Pydantic: stored_file relationship not loaded.")

        return DocumentInDB(
            id=self.id,
            user_document_id=self.user_document_id,
            name=self.name,
            owner_id=self.owner_id,
            access_group=self.access_group,
            access_group_id=self.access_group_id,
            metadata=self.metadata_,
            created=self.created,
            edited=self.edited,
            # Ключевые поля из связанной таблицы:
            extension=self.stored_file.extension,
            content_hash=self.stored_file.content_hash,
            object_path=self.stored_file.object_path
        )