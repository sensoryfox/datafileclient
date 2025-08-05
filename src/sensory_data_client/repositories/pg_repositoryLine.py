import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from sensory_data_client.exceptions import DatabaseError
from sensory_data_client.models.line import Line
from sensory_data_client.db.documentLine_orm import DocumentLineORM
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session

logger = logging.getLogger(__name__)

class LineRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory
    
    async def save_lines(self, doc_id: UUID, lines: list[Line]):
        """
        Сохраняет строки документа, предварительно удалив старые.
        Выполняет операции в одной транзакции.
        """
        if not lines:
            return

        async for session in get_session(self._session_factory):
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
        async for session in get_session(self._session_factory):
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
            
    async def list_all(self,
                       doc_id: UUID | None = None) -> list[Line]:
        """
        Если doc_id указан – возвращает строки только этого документа,
        иначе – все строки во всей базе.
        """
        async for session in get_session(self._session_factory):
            q = select(DocumentLineORM).order_by(
                DocumentLineORM.document_id, DocumentLineORM.position
            )
            if doc_id:
                q = q.where(DocumentLineORM.document_id == doc_id)

            rows = await session.execute(q)
            orms = rows.scalars().all()
            # ORM ➜ Pydantic (to_pydantic не был, конвертируем вручную)
            return [
                Line.model_validate(
                    {
                        "document_id": o.document_id,
                        "block_id":    o.block_id,
                        "position":    o.position,
                        "type":        o.type,
                        "content":     o.content,
                    }
                )
                for o in orms
            ]