# sensory_data_client/db/user_group_membership.py
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, ForeignKey

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base

class UserGroupMembershipORM(Base):
    __tablename__ = "user_group_membership"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(ForeignKey("groups.id"), primary_key=True)