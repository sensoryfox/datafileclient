import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from sensory_data_client.exceptions import DatabaseError
from sensory_data_client.models.document import DocumentInDB
from sensory_data_client.db.document_orm import DocumentORM
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session

logger = logging.getLogger(__name__)

class MetaDataRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
    
    async def check_connection(self):
        """Проверяет соединение с базой данных, выполняя простой запрос."""
        logger.debug("Checking PostgreSQL connection...")
        async for session in get_session(self._session_factory):
            try:
                await session.execute(text("SELECT 1"))
                logger.debug("PostgreSQL connection successful.")
            except SQLAlchemyError as e:
                logger.error(f"PostgreSQL connection failed: {e}")
                raise DatabaseError("Failed to connect to the database.") from e

    async def save(self, doc: DocumentInDB) -> DocumentInDB:
        async for session in get_session(self._session_factory):
            try:
                # 1. Выгружаем данные из Pydantic-модели в словарь.
                model_data = doc.model_dump()
                # 2. Явно "переименовываем" ключ 'metadata' в 'metadata_' 
                model_data['metadata_'] = model_data.pop('metadata')
                # 3. Создаем ORM-объект, используя подготовленный словарь.
                orm = DocumentORM(**model_data)
                session.add(orm)
                await session.commit()
                await session.refresh(orm)
                return orm.to_pydantic()
            except IntegrityError as e:
                await session.rollback()
                raise DatabaseError(str(e)) from e

    async def get(self, doc_id: UUID) -> Optional[DocumentInDB]:
        async for session in get_session(self._session_factory):
            res = await session.execute(select(DocumentORM).where(DocumentORM.id == doc_id))
            orm = res.scalar_one_or_none()
            return orm.to_pydantic() if orm else None

    async def update(self, doc_id: UUID, patch: dict) -> Optional[DocumentInDB]:
        async for session in get_session(self._session_factory):
            try:
                q = (
                    update(DocumentORM)
                    .where(DocumentORM.id == doc_id)
                    .values(**patch, edited=func.now())
                    .returning(DocumentORM)
                )
                res = await session.execute(q)
                await session.commit()
                orm = res.scalar_one_or_none()
                return orm.to_pydantic() if orm else None
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(str(e)) from e

    async def delete(self, doc_id: UUID) -> bool:
        async for session in get_session(self._session_factory):
            res = await session.execute(delete(DocumentORM).where(DocumentORM.id == doc_id))
            await session.commit()
            return res.rowcount > 0

    async def list_all(self,
                       limit: int | None = None,
                       offset: int = 0) -> list[DocumentInDB]:
        """
        Возвращает список документов.  По умолчанию – все.
        Можно пагинировать через limit/offset.
        """
        async for session in get_session(self._session_factory):
            q = select(DocumentORM).order_by(DocumentORM.created.desc()) \
                                   .offset(offset)
            if limit:
                q = q.limit(limit)

            rows = await session.execute(q)
            orms = rows.scalars().all()
            return [o.to_pydantic() for o in orms]