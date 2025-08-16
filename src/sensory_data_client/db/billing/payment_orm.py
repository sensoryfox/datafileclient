# sensory_data_client/db/billing/payment_orm.py
from __future__ import annotations
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import String, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, CreatedAt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .subscription_orm import SubscriptionORM

class PaymentORM(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    subscription_id: Mapped[UUID] = mapped_column(ForeignKey("subscriptions.id"), nullable=False, index=True)
    
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="RUB")

    # Статус платежа: 'succeeded', 'failed', 'pending', 'refunded'.
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Информация от платежного шлюза
    payment_gateway: Mapped[str] = mapped_column(String(100), nullable=True)
    gateway_transaction_id: Mapped[str] = mapped_column(String(255), nullable=True, unique=True, index=True)

    created_at: Mapped[CreatedAt]
    
    # Связь
    subscription: Mapped["SubscriptionORM"] = relationship(back_populates="payments")