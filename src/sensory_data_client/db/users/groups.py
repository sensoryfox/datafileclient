from __future__ import annotations
from uuid import UUID, uuid4

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

class GroupORM(Base):
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)

    users: Mapped[list["UserORM"]] = relationship(
        "UserORM", secondary="user_group_membership", back_populates="groups"
    )
    documents: Mapped[list["DocumentORM"]] = relationship("DocumentORM", back_populates="access_group")