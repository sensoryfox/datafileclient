# sensory_data_client/db/billing/subscription_orm.py
from __future__ import annotations
from uuid import UUID, uuid4
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, CreatedAt, UpdatedAt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..users.users import UserORM
    from .plan_orm import TariffPlanORM
    from .payment_orm import PaymentORM

class SubscriptionORM(Base):
    __tablename__ = "subscriptions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("tariff_plans.id"), nullable=False, index=True)

    # Статус подписки: 'active', 'past_due' (просрочена оплата), 'canceled', 'expired'.
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Период действия подписки
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    
    # Дата отмены. Если не NULL, подписка не будет продлена после expires_at.
    canceled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Цикл оплаты: 'monthly' или 'annually'.
    billing_cycle: Mapped[str] = mapped_column(String(50), nullable=False)
    
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
    
    # Связи
    user: Mapped["UserORM"] = relationship(back_populates="subscriptions", foreign_keys=[user_id])
    plan: Mapped["TariffPlanORM"] = relationship(lazy="joined")
    payments: Mapped[List["PaymentORM"]] = relationship(back_populates="subscription", cascade="all, delete-orphan")