from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List
from sqlalchemy import Index, Boolean, text
from sqlalchemy import String, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from sensory_data_client.db.base import Base, CreatedAt, UpdatedAt
from sensory_data_client.models.document import DocumentInDB
from sensory_data_client.db.documents.document_permissions import DocumentPermissionORM
from sensory_data_client.db.tags.tag_orm import TagORM

class DocumentORM(Base):
    __tablename__ = "documents"

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
    
    created: Mapped[CreatedAt]
    edited: Mapped[UpdatedAt]
    
    is_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"), comment="Флаг, разрешающий синхронизацию документа с Elasticsearch")
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default=text("false"))
    
    permissions: Mapped[List["DocumentPermissionORM"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    tags: Mapped[List["TagORM"]] = relationship(
        secondary="document_tags", back_populates="documents", lazy="selectin"
    )
    
    owner: Mapped["UserORM"] = relationship("UserORM", back_populates="documents_owned")
    access_group: Mapped[Optional["GroupORM"]] = relationship("GroupORM", back_populates="documents", lazy="joined")
    stored_file: Mapped["StoredFileORM"] = relationship("StoredFileORM", back_populates="documents", lazy="joined")

    lines: Mapped[list["DocumentLineORM"]] = relationship("DocumentLineORM", back_populates="document", cascade="all, delete-orphan")
    images: Mapped[list["DocumentImageORM"]] = relationship("DocumentImageORM", back_populates="document", cascade="all, delete-orphan")
    permissions: Mapped[list["DocumentPermissionORM"]] = relationship("DocumentPermissionORM", back_populates="document", cascade="all, delete-orphan")
    
    
    __table_args__ = (
        UniqueConstraint("owner_id", "user_document_id", name="uq_documents_owner_userdoc"),
        Index("idx_documents_owner_id", "owner_id"),
        Index("idx_documents_access_group_id", "access_group_id"),
    )
    
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
            is_sync_enabled=self.is_sync_enabled,
            # Ключевые поля из связанной таблицы:
            extension=self.stored_file.extension,
            content_hash=self.stored_file.content_hash,
            object_path=self.stored_file.object_path
        )
        
        