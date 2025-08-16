# sensory_data_client/repositories/pg_repositoryTag.py

import logging
from uuid import UUID
from typing import List
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db import TagORM, DocumentTagORM, DocumentORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

class TagRepository:
    """
    Репозиторий для управления тегами и их связями с документами.
    """
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def _find_or_create_tags(self, session: AsyncSession, tag_names: List[str]) -> List[TagORM]:
        """
        Вспомогательный метод. Находит существующие теги или создает новые в рамках
        одной сессии. Нормализует имена тегов.
        """
        normalized_names = {name.lower().strip() for name in tag_names if name.strip()}
        if not normalized_names:
            return []

        stmt = select(TagORM).where(TagORM.name.in_(normalized_names))
        result = await session.execute(stmt)
        existing_tags = result.scalars().all()
        existing_names = {tag.name for tag in existing_tags}

        new_names = normalized_names - existing_names
        new_tags = [TagORM(name=name) for name in new_names]

        if new_tags:
            session.add_all(new_tags)
            await session.flush()

        return existing_tags + new_tags

    async def add_tags_to_document(
        self,
        doc_id: UUID,
        tags: List[str],
        source: str = "manual"
    ):
        """
        Привязывает список тегов к документу.
        """
        async for session in get_session(self._session_factory):
            try:
                tag_orms = await self._find_or_create_tags(session, tags)
                if not tag_orms:
                    return

                associations = [
                    DocumentTagORM(doc_id=doc_id, tag_id=tag.id, source=source)
                    for tag in tag_orms
                ]
                
                for assoc in associations:
                    await session.merge(assoc)
                
                await session.commit()
                logger.info(f"Added/updated {len(tags)} tags for document {doc_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to add tags for document {doc_id}: {e}")
                raise DatabaseError(f"Failed to add tags: {e}")

    async def get_document_tags(self, doc_id: UUID) -> List[TagORM]:
        """
        Возвращает все теги, связанные с документом.
        """
        async for session in get_session(self._session_factory):
            stmt = select(DocumentORM).options(
                selectinload(DocumentORM.tags)
            ).where(DocumentORM.id == doc_id)
            
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            return document.tags if document else []
        
    async def set_tag_vector(self, tag_id: UUID, vector: List[float]):
        """
        Устанавливает или обновляет вектор для существующего тега.
        """
        stmt = (
            update(TagORM)
            .where(TagORM.id == tag_id)
            .values(vector=vector)
        )
        async for session in get_session(self._session_factory):
            try:
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Set vector for tag {tag_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to set vector for tag {tag_id}: {e}")
                raise DatabaseError(f"Failed to set vector for tag: {e}")