# sensory_data_client/repositories/pg_repositoryPermission.py

import logging
from uuid import UUID
from typing import List
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db import DocumentPermissionORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

class PermissionRepository:
    """
    Репозиторий для управления явными правами доступа к документам.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def grant_permission(
        self,
        doc_id: UUID,
        user_id: UUID,
        permission_level: str = "read"
    ):
        """
        Предоставляет или обновляет право доступа пользователя к документу.
        Метод идемпотентен: если право уже существует, оно будет обновлено.
        """
        permission = DocumentPermissionORM(
            doc_id=doc_id,
            user_id=user_id,
            permission_level=permission_level
        )
        
        async for session in get_session(self._session_factory):
            try:
                # session.merge() атомарно вставит или обновит запись на основе
                # ограничений уникальности, что идеально для идемпотентности.
                await session.merge(permission)
                await session.commit()
                logger.info(f"Granted '{permission_level}' permission for doc {doc_id} to user {user_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to grant permission for doc {doc_id} to user {user_id}: {e}")
                raise DatabaseError(f"Failed to grant permission: {e}")

    async def revoke_permission(self, doc_id: UUID, user_id: UUID):
        """
        Отзывает право доступа пользователя к документу.
        """
        stmt = delete(DocumentPermissionORM).where(
            DocumentPermissionORM.doc_id == doc_id,
            DocumentPermissionORM.user_id == user_id
        )
        async for session in get_session(self._session_factory):
            try:
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Revoked permission for doc {doc_id} from user {user_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to revoke permission for doc {doc_id} from user {user_id}: {e}")
                raise DatabaseError(f"Failed to revoke permission: {e}")

    async def get_user_shared_doc_ids(self, user_id: UUID) -> List[UUID]:
        """
        Возвращает список ID документов, к которым пользователю предоставлен явный доступ.
        Это ключевой метод для построения ACL-фильтра в поиске.
        """
        stmt = select(DocumentPermissionORM.doc_id).where(
            DocumentPermissionORM.user_id == user_id
        )
        async for session in get_session(self._session_factory):
            result = await session.execute(stmt)
            return result.scalars().all()