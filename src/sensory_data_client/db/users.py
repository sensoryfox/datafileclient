# sensory_data_client/db/users.py
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sensory_data_client.db.base import Base
class UserORM(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(PG_UUID, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Связь с группами
    groups = relationship("GroupORM", secondary="user_group_membership", back_populates="users")