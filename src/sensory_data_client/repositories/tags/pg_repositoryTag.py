# sensory_data_client/repositories/pg_repositoryTag.py

import logging
from uuid import UUID
from typing import List, Iterable
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db import TagORM, DocumentTagORM, DocumentORM
from sensory_data_client.db.base import get_session
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

def _normalize_names(names: Iterable[str]) -> List[str]:
    out: list[str] = []
    seen: set[str] = set()
    for n in names or []:
        if not n:
            continue
        x = n.strip()
        if x.startswith("#"):
            x = x[1:]
        x = x.strip().lower()
        if not x:
            continue
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


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
        normalized = _normalize_names(tags)
        async with get_session(self._session_factory) as session:
            try:
                tag_orms = await self._find_or_create_tags(session, normalized)
                if not tag_orms:
                    return

                associations = [
                    DocumentTagORM(doc_id=doc_id, tag_id=tag.id, source=source)
                    for tag in tag_orms
                ]
                
                for assoc in associations:
                    await session.merge(assoc)
                
                await session.commit()
                logger.info(f"Added/updated {len(normalized)} tags for document {doc_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to add tags for document {doc_id}: {e}")
                raise DatabaseError(f"Failed to add tags: {e}")

    async def get_document_tags(self, doc_id: UUID) -> List[TagORM]:
        """
        Возвращает все теги, связанные с документом.
        """
        async with get_session(self._session_factory) as session:
            stmt = select(DocumentORM).options(
                selectinload(DocumentORM.tags)
            ).where(DocumentORM.id == doc_id)
            
            result = await session.execute(stmt)
            document = result.scalar_one_or_none()
            
            return document.tags if document else []

    async def get_names_by_doc(self, doc_id: UUID) -> List[str]:
        async with get_session(self._session_factory) as session:
            try:
                from sqlalchemy import select
                stmt = (
                select(TagORM.name)
                .join(DocumentTagORM, DocumentTagORM.tag_id == TagORM.id)
                .where(DocumentTagORM.doc_id == doc_id)
                )
                res = await session.execute(stmt)
                return list(res.scalars().all() or [])
            except SQLAlchemyError as e:
                logger.error("get_names_by_doc failed for doc %s: %s", str(doc_id), e)
                return []
            
    async def set_tag_vector(self, tag_id: UUID, vector: List[float]):
        """
        Устанавливает или обновляет вектор для существующего тега.
        """
        stmt = (
            update(TagORM)
            .where(TagORM.id == tag_id)
            .values(vector=vector)
        )
        async with get_session(self._session_factory) as session:
            try:
                await session.execute(stmt)
                await session.commit()
                logger.info(f"Set vector for tag {tag_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to set vector for tag {tag_id}: {e}")
                raise DatabaseError(f"Failed to set vector for tag: {e}")
            
            
    async def ensure_many(self, names: Iterable[str]) -> List[TagORM]:
        """
        Гарантирует существование тегов с именами из names. Возвращает объекты TagORM для всех names.
        Имена нормализуются (lower-case, без '#').
        """
        normalized = _normalize_names(names)
        if not normalized:
            return []

        async with get_session(self._session_factory) as session:
            # Вставляем отсутствующие (ON CONFLICT DO NOTHING)
            values = [{"name": n} for n in normalized]
            stmt = pg_insert(TagORM.__table__).values(values).on_conflict_do_nothing(index_elements=["name"])
            await session.execute(stmt)
            await session.commit()

            # Вычитываем все (и ранее существующие, и вновь созданные)
            res = await session.execute(select(TagORM).where(TagORM.name.in_(normalized)))
            tags = list(res.scalars().all() or [])
            return tags
        
    async def attach_to_document(self, doc_id: UUID, tag_ids: List[UUID], source: str = "auto") -> None:
        """
        Привязывает к документу теги, игнорируя уже существующие пары (doc_id, tag_id).
        """
        if not tag_ids:
            return

        async with get_session(self._session_factory) as session:
            values = [{"doc_id": doc_id, "tag_id": tid, "source": source} for tid in tag_ids]
            stmt = (
                pg_insert(DocumentTagORM.__table__)
                .values(values)
                .on_conflict_do_nothing(index_elements=["doc_id", "tag_id"])
            )
            await session.execute(stmt)
            await session.commit()
