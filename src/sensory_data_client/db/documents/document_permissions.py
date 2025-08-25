# sensory_data_client/db/document_permissions.py
from uuid import UUID, uuid4
from sqlalchemy import String, ForeignKey, Integer, UniqueConstraint


from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base, CreatedAt

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .document_orm import DocumentORM
    from ..users.users import UserORM
    
class DocumentPermissionORM(Base):
    __tablename__ = "document_permissions"
    
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    doc_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission_level: Mapped[str] = mapped_column(String(50), nullable=False, default="read")
    created_at: Mapped[CreatedAt]
    
    __table_args__ = (UniqueConstraint("doc_id", "user_id", "permission_level", name="uq_document_permissions"),)

    document: Mapped["DocumentORM"] = relationship(back_populates="permissions")
    user: Mapped["UserORM"] = relationship(back_populates="permissions")
    