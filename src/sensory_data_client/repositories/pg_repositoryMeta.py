import logging
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from sensory_data_client.exceptions import DatabaseError, DocumentNotFoundError
from sensory_data_client.models.document import DocumentInDB
from sensory_data_client.db.documents.document_orm import DocumentORM
from sensory_data_client.db.documents.storage_orm import StoredFileORM
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session

logger = logging.getLogger(__name__)

class MetaDataRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
    
    async def check_connection(self):
        """Проверяет соединение с базой данных, выполняя простой запрос."""
        logger.debug("Checking PostgreSQL connection...")
        async with get_session(self._session_factory) as session:
            try:
                await session.execute(text("SELECT 1"))
                logger.debug("PostgreSQL connection successful.")
            except SQLAlchemyError as e:
                logger.error(f"PostgreSQL connection failed: {e}")
                raise DatabaseError("Failed to connect to the database.") from e

    async def save(self, doc: DocumentORM) -> DocumentORM:
        async with get_session(self._session_factory) as session:
            try:
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
                return doc
            except IntegrityError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to save document metadata: {e}") from e

    async def get(self, doc_id: UUID) -> Optional[DocumentInDB]:
        async with get_session(self._session_factory) as session:
            res = await session.execute(select(DocumentORM).where(DocumentORM.id == doc_id))
            orm = res.scalar_one_or_none()
            return orm.to_pydantic() if orm else None
        
    async def get_orm(self, doc_id: UUID) -> Optional[DocumentORM]:
        async with get_session(self._session_factory) as session:
            res = await session.execute(select(DocumentORM).where(DocumentORM.id == doc_id))
            orm = res.scalar_one_or_none()
            return orm if orm else None

    async def update(self, doc_id: UUID, patch: dict) -> Optional[DocumentInDB]:
        async with get_session(self._session_factory) as session:
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

    async def get_brief(self, doc_id: UUID) -> Dict[str, Any]:
        """Вернуть только name и metadata_ документа. Никаких ORM-объектов наружу."""
        async with get_session(self._session_factory) as session:
            try:
                stmt = select(DocumentORM.name, DocumentORM.metadata_).where(DocumentORM.id == doc_id)
                row = (await session.execute(stmt)).one_or_none()
                if not row:
                    return {"name": None, "metadata_": {}}
                name, metadata_ = row
                return {"name": name, "metadata_": metadata_ or {}}
            except SQLAlchemyError as e:
                logger.error("get_brief failed for %s: %s", doc_id, e)
                return {"name": None, "metadata_": {}}

    async def update_metadata(self, doc_id: UUID, metadata_: Dict[str, Any]) -> None:
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    update(DocumentORM)
                    .where(DocumentORM.id == doc_id)
                    .values({DocumentORM.metadata_: metadata_})  # используем ORM-атрибут
                )
                res = await session.execute(stmt)
                if res.rowcount == 0:
                    raise ValueError(f"Document {doc_id} not found")
                await session.commit()
            except Exception as e:
                logger.error("update_metadata failed for %s: %s", doc_id, e)
                await session.rollback()
                raise
            
    async def delete(self, doc_id: UUID) -> bool:
        async with get_session(self._session_factory) as session:
            res = await session.execute(delete(DocumentORM).where(DocumentORM.id == doc_id))
            await session.commit()
            return res.rowcount > 0

    async def get_stored_file_by_hash(self, content_hash: str) -> StoredFileORM | None:
        async with get_session(self._session_factory) as session:
            stmt = select(StoredFileORM).where(StoredFileORM.content_hash == content_hash)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def save_new_physical_file(self, stored_file: StoredFileORM, document: DocumentORM):
        """
        Транзакционно сохраняет и физический файл, и логический документ.
        Используется, когда файл действительно новый.
        """
        async with get_session(self._session_factory) as session:
            session.add(stored_file)
            session.add(document)
            await session.commit()
            # Обновляем объект document, чтобы он содержал все данные из БД
            await session.refresh(document)
            
    async def find_parsed_doc_by_hash(self, content_hash: str, exclude_doc_id: UUID) -> Optional[DocumentORM]:
        """
        Находит документ с таким же хешем, у которого есть строки, исключая текущий документ.
        """
        async with get_session(self._session_factory) as session:
            stmt = (
                select(DocumentORM)
                .join(DocumentORM.stored_file)
                .join(DocumentORM.lines)
                .where(
                    StoredFileORM.content_hash == content_hash,
                    DocumentORM.id != exclude_doc_id
                )
                .limit(1)
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
     
    async def get_sync_status(self, doc_id: UUID) -> bool:
        """
        Эффективно запрашивает только флаг is_sync_enabled для документа.
        Возвращает False, если документ не найден.
        """
        async with get_session(self._session_factory) as session:
            stmt = select(DocumentORM.is_sync_enabled).where(DocumentORM.id == doc_id)
            result = await session.execute(stmt)
            status = result.scalar_one_or_none()
            return status if status is not None else False   
        
    async def set_sync_status(self, doc_id: UUID, is_enabled: bool) -> Optional[DocumentInDB]:
        """
        Обновляет флаг is_sync_enabled для документа и возвращает обновленный объект.
        """
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    update(DocumentORM)
                    .where(DocumentORM.id == doc_id)
                    .values(is_sync_enabled=is_enabled)
                    .returning(DocumentORM) # Возвращаем всю ORM-строку
                )
                result = await session.execute(stmt)
                await session.commit()
                
                updated_orm = result.scalar_one_or_none()
                if not updated_orm:
                    # Если ничего не обновилось, значит документа нет
                    raise DocumentNotFoundError(f"Document with id {doc_id} not found.")
                
                return updated_orm.to_pydantic()

            except SQLAlchemyError as e:
                await session.rollback()
                logger.error(f"Failed to set sync status for doc {doc_id}: {e}")
                raise DatabaseError(f"Failed to set sync status: {e}")

    async def is_stored_file_orphan(self, stored_file_id: int) -> bool:
        """Проверяет, остались ли документы, ссылающиеся на данный StoredFile."""
        async with get_session(self._session_factory) as session:
            stmt = select(func.count(DocumentORM.id)).where(DocumentORM.stored_file_id == stored_file_id)
            result = await session.execute(stmt)
            count = result.scalar_one()
            return count == 0
        
    async def list_all(self,
                       limit: int | None = None,
                       offset: int = 0) -> list[DocumentInDB]:
        """
        Возвращает список документов.  По умолчанию – все.
        Можно пагинировать через limit/offset.
        """
        async with get_session(self._session_factory) as session:
            q = select(DocumentORM).order_by(DocumentORM.created.desc()) \
                                   .offset(offset)
            if limit:
                q = q.limit(limit)

            rows = await session.execute(q)
            orms = rows.scalars().all()
            return [o.to_pydantic() for o in orms]