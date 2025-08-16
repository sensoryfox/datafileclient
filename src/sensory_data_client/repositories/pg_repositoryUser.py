# src/db/pg_repositoryUser.py

import logging
from uuid import UUID
from typing import Optional
from sqlalchemy.orm import joinedload

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from passlib.context import CryptContext # Для хеширования паролей

from sensory_data_client.db import UserORM, SubscriptionORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

# Контекст для работы с паролями, лучше вынести в общий auth-модуль, но для простоты здесь
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    """Создает хеш из обычного пароля."""
    return pwd_context.hash(password)


class UserRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def create_user(self, email: str, plain_password: str, status: str = "pending_verification") -> UserORM:
        """
        Создает нового пользователя.
        :param status: Начальный статус пользователя (например, 'pending_verification' или 'active').
        """
        hashed_password = get_password_hash(plain_password)
        user = UserORM(
            email=email,
            hashed_password=hashed_password,
            status=status
        )
        async for session in get_session(self._session_factory):
            try:
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return user
            except IntegrityError as e:
                await session.rollback()
                # Перевыбрасываем как кастомное исключение, чтобы API мог его поймать
                raise DatabaseError(f"User with email {email} already exists.") from e
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to create user: {e}") from e

    async def get_by_id(self, user_id: UUID) -> Optional[UserORM]:
        """Находит пользователя по его UUID."""
        async for session in get_session(self._session_factory):
            result = await session.execute(select(UserORM).where(UserORM.id == user_id))
            return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[UserORM]:
        """Находит пользователя по email."""
        async for session in get_session(self._session_factory):
            result = await session.execute(select(UserORM).where(UserORM.email == email))
            return result.scalar_one_or_none()
        

    async def update_user_status(self, user_id: UUID, new_status: str) -> Optional[UserORM]:
        """
        Обновляет статус пользователя (active, suspended и т.д.).
        Возвращает обновленный объект пользователя или None, если пользователь не найден.
        """
        async for session in get_session(self._session_factory):
            try:
                stmt = (
                    update(UserORM)
                    .where(UserORM.id == user_id)
                    .values(status=new_status)
                    .returning(UserORM)
                )
                result = await session.execute(stmt)
                await session.commit()
                updated_user = result.scalar_one_or_none()
                if updated_user:
                    logger.info(f"Updated status for user {user_id} to '{new_status}'")
                return updated_user
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Database error on updating user status: {e}")
                raise DatabaseError(f"Failed to update status for user {user_id}: {e}")

    async def get_user_with_subscription(self, user_id: UUID) -> Optional[UserORM]:
        """
        Находит пользователя и жадно (eagerly) загружает его текущую активную
        подписку и связанный с ней тарифный план.
        Это предотвращает N+1 запросы при проверке прав доступа.
        """
        async for session in get_session(self._session_factory):
            stmt = (
                select(UserORM)
                .where(UserORM.id == user_id)
                .options(
                    joinedload(UserORM.current_subscription)
                    .joinedload(SubscriptionORM.plan)
                )
            )
            result = await session.execute(stmt)
            # scalars().first() - правильный способ получить один или ни одного объекта
            return result.scalars().first()