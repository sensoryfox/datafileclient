# sensory_data_client/db/groups.py
from uuid import UUID, uuid4
from sqlalchemy import String

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base

class GroupORM(Base):
    __tablename__ = "groups"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    # Связь с пользователями
    users = relationship("UserORM", secondary="user_group_membership", back_populates="groups")