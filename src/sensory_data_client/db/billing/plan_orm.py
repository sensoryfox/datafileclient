# sensory_data_client/db/billing/plan_orm.py
from __future__ import annotations
from uuid import UUID, uuid4
from sqlalchemy import String, Boolean, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, CreatedAt, UpdatedAt

class TariffPlanORM(Base):
    __tablename__ = "tariff_plans"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)

    # Цены. Используем Numeric для точности.
    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)
    price_annually: Mapped[float] = mapped_column(Numeric(10, 2), nullable=True)

    # Флаг для архивации тарифов, чтобы не удалять их из истории подписок.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Ключевое поле: возможности и лимиты тарифа в формате JSON.
    # Пример: {"max_docs": 100, "max_groups": 5, "ocr_enabled": true, "max_file_size_mb": 50}
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')

    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]