from __future__ import annotations
from uuid import UUID, uuid4

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base

class UserGroupMembershipORM(Base):
    __tablename__ = "user_group_membership"
    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_user_group_membership"),)

    user: Mapped["UserORM"] = relationship(back_populates="memberships")
    group: Mapped["GroupORM"] = relationship(back_populates="memberships")