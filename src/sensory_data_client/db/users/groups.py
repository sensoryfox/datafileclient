from __future__ import annotations
from uuid import UUID, uuid4
from typing import List, Optional 

from sqlalchemy import String, Text 
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAt, UpdatedAt

class GroupORM(Base):
    __tablename__ = "groups"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[CreatedAt]
    edited_at: Mapped[UpdatedAt]
    memberships: Mapped[List["UserGroupMembershipORM"]] = relationship(
            back_populates="group", cascade="all, delete-orphan"
        )
    users: Mapped[List["UserORM"]] = relationship(
            secondary="user_group_membership",
            viewonly=True # Только для чтения
        )
    documents: Mapped[list["DocumentORM"]] = relationship("DocumentORM", back_populates="access_group")