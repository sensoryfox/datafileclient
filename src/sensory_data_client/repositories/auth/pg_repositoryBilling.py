# sensory_data_client/repositories/pg_repositoryBilling.py

import logging
from uuid import UUID
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

from sensory_data_client.db import TariffPlanORM, SubscriptionORM, PaymentORM, UserORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError, NotFoundError

logger = logging.getLogger(__name__)

class BillingRepository:
    """
    Репозиторий для управления тарифными планами, подписками и платежами.
    """
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get_plan_by_id(self, plan_id: UUID) -> Optional[TariffPlanORM]:
        """Находит тарифный план по ID."""
        async with get_session(self._session_factory) as session:
            return await session.get(TariffPlanORM, plan_id)

    async def list_active_plans(self) -> List[TariffPlanORM]:
        """Возвращает список всех активных (не архивных) тарифных планов."""
        async with get_session(self._session_factory) as session:
            stmt = select(TariffPlanORM).where(TariffPlanORM.is_active == True).order_by(TariffPlanORM.price_monthly)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def get_subscription_with_details(self, subscription_id: UUID) -> Optional[SubscriptionORM]:
        """Находит подписку и подгружает связанные с ней план и платежи."""
        async with get_session(self._session_factory) as session:
            stmt = (
                select(SubscriptionORM)
                .where(SubscriptionORM.id == subscription_id)
                .options(
                    joinedload(SubscriptionORM.plan),
                    joinedload(SubscriptionORM.payments)
                )
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def find_expired_subscriptions(self) -> List[SubscriptionORM]:
        """Находит активные подписки, срок действия которых уже истек."""
        now = datetime.now()
        async with get_session(self._session_factory) as session:
            stmt = (
                select(SubscriptionORM)
                .where(
                    SubscriptionORM.status == 'active',
                    SubscriptionORM.expires_at < now
                )
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def update_subscription_status(self, subscription_id: UUID, new_status: str) -> Optional[SubscriptionORM]:
        """Обновляет статус подписки."""
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    update(SubscriptionORM)
                    .where(SubscriptionORM.id == subscription_id)
                    .values(status=new_status)
                    .returning(SubscriptionORM)
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.scalar_one_or_none()
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to update status for subscription {subscription_id}: {e}")

    async def activate_subscription_transaction(
        self,
        user_id: UUID,
        plan_id: UUID,
        payment_data: dict,
        subscription_data: dict
    ) -> SubscriptionORM:
        """
        Выполняет всю логику активации подписки в одной транзакции.
        1. Находит пользователя.
        2. Создает платеж (PaymentORM).
        3. Создает подписку (SubscriptionORM).
        4. Связывает их друг с другом и с пользователем.
        5. Обновляет поле `current_subscription_id` у пользователя.
        """
        async with get_session(self._session_factory) as session:
            try:
                # Шаг 1: Получаем пользователя, чтобы обновить его
                user = await session.get(UserORM, user_id)
                if not user:
                    raise NotFoundError(f"User with id {user_id} not found for subscription activation.")

                # Шаг 2: Создаем платеж
                payment = PaymentORM(**payment_data)

                # Шаг 3: Создаем подписку
                subscription = SubscriptionORM(**subscription_data)

                # Шаг 4: Устанавливаем связи
                subscription.payments.append(payment)
                user.subscriptions.append(subscription)
                
                # Шаг 5: Обновляем быструю ссылку у пользователя
                user.current_subscription_id = subscription.id
                
                session.add(user) # Добавляем пользователя, остальное применится каскадом
                
                await session.commit()
                
                # Обновляем объект, чтобы он содержал ID и другие поля из БД
                await session.refresh(subscription)
                await session.refresh(user)
                
                logger.info(f"Successfully activated subscription {subscription.id} for user {user_id}")
                return subscription
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Transaction failed while activating subscription for user {user_id}: {e}")
                raise DatabaseError("Subscription activation failed due to a database error.")