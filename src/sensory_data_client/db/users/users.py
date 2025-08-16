from __future__ import annotations
from uuid import UUID, uuid4
from typing import List, Optional 

from sqlalchemy import String, Boolean, ForeignKey 
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAt
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..documents.document_orm import DocumentORM
    from ..documents.document_permissions import DocumentPermissionORM
    from .groups import GroupORM
    from ..billing.subscription_orm import SubscriptionORM # <--- Импортируем подписку


class UserORM(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[CreatedAt]
    is_superuser: Mapped[bool] = mapped_column(default=False)
    
    # 1. Статус пользователя.
    # 'active' - может входить и работать.
    # 'suspended' - заблокирован (например, за неуплату или админом).
    # 'pending_verification' - зарегистрировался, но не подтвердил email.
    status: Mapped[str] = mapped_column(String(50), default="pending_verification", nullable=False, index=True)
    # 2. Системная роль пользователя.
    # 'user' - стандартный пользователь.
    # 'admin' - может управлять пользователями, тарифами и т.д.
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False)
    # 3. Ссылка на ТЕКУЩУЮ АКТИВНУЮ подписку.
    # Это небольшая денормализация для производительности. Позволяет не искать
    # активную подписку среди всех в истории, а сразу получить к ней доступ.
    # Обновляется при успешной оплате или отмене подписки.
    current_subscription_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("subscriptions.id", use_alter=True), nullable=True
    )
    
    current_subscription: Mapped[Optional["SubscriptionORM"]] = relationship(
        foreign_keys=[current_subscription_id]
    )
    # Связь "один-ко-многим" со ВСЕМИ подписками пользователя (история).
    subscriptions: Mapped[List["SubscriptionORM"]] = relationship(
        back_populates="user",
        foreign_keys="SubscriptionORM.user_id", # Явно указываем foreign key
        cascade="all, delete-orphan"
    )
    
    groups: Mapped[list["GroupORM"]] = relationship(
        "GroupORM", secondary="user_group_membership", back_populates="users"
    )
    documents_owned: Mapped[list["DocumentORM"]] = relationship("DocumentORM", back_populates="owner")
    permissions: Mapped[list["DocumentPermissionORM"]] = relationship(
        "DocumentPermissionORM", back_populates="user", cascade="all, delete-orphan"
    )