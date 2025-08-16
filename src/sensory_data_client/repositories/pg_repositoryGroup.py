# Файл: sensory_data_client/repositories/pg_repositoryGroup.py

import logging
from uuid import UUID
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import selectinload

from sensory_data_client.db import UserORM, GroupORM, UserGroupMembershipORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError, NotFoundError
from sensory_data_client.models.group import GroupCreate
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

class GroupRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def create_group(self, group_data: GroupCreate) -> GroupORM:
        """Создает новую группу."""
        new_group = GroupORM(**group_data.model_dump())
        async for session in get_session(self._session_factory):
            try:
                session.add(new_group)
                await session.commit()
                await session.refresh(new_group)
                logger.info(f"Created group '{new_group.name}' with id {new_group.id}")
                return new_group
            except IntegrityError:
                await session.rollback()
                raise DatabaseError(f"Group with name '{group_data.name}' already exists.")
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to create group: {e}")

    async def get_group_by_id(self, group_id: UUID, with_members: bool = False) -> Optional[GroupORM]:
        """Находит группу по ID. Опционально подгружает ее участников."""
        async for session in get_session(self._session_factory):
            query = select(GroupORM).where(GroupORM.id == group_id)
            if with_members:
                # selectinload - эффективный способ загрузить связанные объекты
                query = query.options(selectinload(GroupORM.users))
            
            result = await session.execute(query)
            return result.scalar_one_or_none()
            
    async def list_groups(self) -> List[GroupORM]:
        """Возвращает список всех групп."""
        async for session in get_session(self._session_factory):
            result = await session.execute(select(GroupORM).order_by(GroupORM.name))
            return list(result.scalars().all())

    async def add_user_to_group(self, user_id: UUID, group_id: UUID) -> None:
        """Добавляет пользователя в группу."""
        async for session in get_session(self._session_factory):
            # SQLAlchemy 2.0 style: используем relationship для добавления
            group = await session.get(GroupORM, group_id, options=[selectinload(GroupORM.users)])
            if not group:
                raise NotFoundError(f"Group with id {group_id} not found.")

            user = await session.get(UserORM, user_id)
            if not user:
                raise NotFoundError(f"User with id {user_id} not found.")

            if user not in group.users:
                group.users.append(user)
                try:
                    await session.commit()
                    logger.info(f"Added user {user_id} to group {group_id}")
                except SQLAlchemyError as e:
                    await session.rollback()
                    raise DatabaseError(f"Failed to add user to group: {e}")
            else:
                logger.warning(f"User {user_id} is already in group {group_id}")
    
    async def remove_user_from_group(self, user_id: UUID, group_id: UUID) -> None:
        """Удаляет пользователя из группы."""
        async for session in get_session(self._session_factory):
            group = await session.get(GroupORM, group_id, options=[selectinload(GroupORM.users)])
            if not group:
                raise NotFoundError(f"Group with id {group_id} not found.")
                
            user_to_remove = next((u for u in group.users if u.id == user_id), None)
            
            if user_to_remove:
                group.users.remove(user_to_remove)
                try:
                    await session.commit()
                    logger.info(f"Removed user {user_id} from group {group_id}")
                except SQLAlchemyError as e:
                    await session.rollback()
                    raise DatabaseError(f"Failed to remove user from group: {e}")
            else:
                logger.warning(f"User {user_id} was not in group {group_id}")

    async def get_user_groups(self, user_id: UUID) -> List[GroupORM]:
        """Получает все группы, в которых состоит пользователь."""
        async for session in get_session(self._session_factory):
            query = select(UserORM).where(UserORM.id == user_id).options(selectinload(UserORM.groups))
            user = (await session.execute(query)).scalar_one_or_none()
            if not user:
                raise NotFoundError(f"User with id {user_id} not found.")
            return user.groups if user else []