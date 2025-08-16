import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from sensory_data_client.exceptions import DatabaseError
from sensory_data_client.models.document import DocumentInDB
from sensory_data_client.db.documents.document_orm import DocumentORM
from sensory_data_client.db.documents.storage_orm import StoredFileORM
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session

logger = logging.getLogger(__name__)

class ObjectRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get_stored_file_by_hash(self, content_hash: str) -> StoredFileORM | None:
        async for session in get_session(self._session_factory):
            stmt = select(StoredFileORM).where(StoredFileORM.content_hash == content_hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def save_new_physical_file(self, stored_file: StoredFileORM, document: DocumentORM):
        """
        Транзакционно сохраняет и физический файл, и логический документ.
        Используется, когда файл действительно новый.
        """
        async for session in get_session(self._session_factory):
            session.add(stored_file)
            session.add(document)
            await session.commit()
            # Обновляем объект document, чтобы он содержал все данные из БД
            await session.refresh(document)
            

    async def list_all(self,
                                limit: int | None = None,
                                offset: int = 0) -> list[StoredFileORM]:
        """
        Возвращает список всех физически сохраненных файлов (StoredFileORM).
        Можно пагинировать через limit/offset.
        """
        async for session in get_session(self._session_factory):
            q = select(StoredFileORM).order_by(StoredFileORM.first_uploaded_at.desc()) \
                                   .offset(offset)
            if limit:
                q = q.limit(limit)

            result = await session.execute(q)
            return list(result.scalars().all())