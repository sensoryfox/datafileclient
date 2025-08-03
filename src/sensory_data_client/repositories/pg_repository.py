import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..exceptions import DatabaseError
from ..models.document import DocumentInDB, DocumentCreate, Line
from ..db.document_orm import DocumentORM
from ..db.document_orm import DocumentLineORM
from ..db.base import get_session

logger = logging.getLogger(__name__)

class PostgresRepository:
    async def save(self, doc: DocumentInDB) -> DocumentInDB:
        async for session in get_session():
            try:
                orm = DocumentORM(**doc.model_dump(exclude={"metadata"}, metadata_=doc.metadata))
                session.add(orm)
                await session.commit()
                await session.refresh(orm)
                return orm.to_pydantic()
            except IntegrityError as e:
                await session.rollback()
                raise DatabaseError(str(e)) from e

    async def get(self, doc_id: UUID) -> Optional[DocumentInDB]:
        async for session in get_session():
            res = await session.execute(select(DocumentORM).where(DocumentORM.id == doc_id))
            orm = res.scalar_one_or_none()
            return orm.to_pydantic() if orm else None

    async def update(self, doc_id: UUID, patch: dict) -> Optional[DocumentInDB]:
        async for session in get_session():
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
        async for session in get_session():
            res = await session.execute(delete(DocumentORM).where(DocumentORM.id == doc_id))
            await session.commit()
            return res.rowcount > 0

    async def save_lines(self, doc_id: UUID, lines: list[Line]):
        """
        Сохраняет строки документа, предварительно удалив старые.
        Выполняет операции в одной транзакции.
        """
        if not lines:
            return

        async for session in get_session():
            try:
                # 1. Удаляем все предыдущие строки для этого документа
                await session.execute(
                    delete(DocumentLineORM).where(DocumentLineORM.document_id == doc_id)
                )

                # 2. Готовим данные для bulk-вставки
                line_dicts = [
                    {**line.model_dump(), "document_id": doc_id} for line in lines
                ]
                
                # 3. Выполняем bulk-вставку
                await session.execute(insert(DocumentLineORM), line_dicts)
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to save lines for document {doc_id}: {e}") from e

    async def update_lines(self, doc_id: UUID, block_id: str, new_content: str) -> bool:
        """
        Находит строку по ID документа и ID блока (например, изображения) и обновляет ее контент.
        Используется для добавления alt-текста.
        """
        async for session in get_session():
            try:
                res = await session.execute(
                    update(DocumentLineORM)
                    .where(DocumentLineORM.document_id == doc_id, DocumentLineORM.block_id == block_id)
                    .values(content=new_content)
                )
                await session.commit()
                return res.rowcount > 0
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to update line content for block {block_id}: {e}") from e