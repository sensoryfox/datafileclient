import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, update, delete, insert, func
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from sensory_data_client.exceptions import DatabaseError
from sensory_data_client.models.line import Line
from sensory_data_client.db.documents.documentLine_orm import DocumentLineORM
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session

from sqlalchemy.dialects.postgresql import insert as pg_insert

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
                    delete(DocumentLineORM).where(DocumentLineORM.doc_id == doc_id)
                )

                # 2. Готовим данные для bulk-вставки
                line_dicts = [
                    {
                        "doc_id": doc_id,
                        "position": line.line_no, # Явно указываем, что line_no идет в position
                        "page_idx": line.page_idx,
                        "block_id": line.block_id,
                        "block_type": line.block_type,
                        "content": line.content,
                        "geometry": { # Собираем геометрию в один JSON-объект
                            "polygon": line.polygon,
                            "bbox": line.bbox,
                        },
                        "hierarchy": line.hierarchy,
                        "sheet_name": line.sheet_name
                    }
                    for line in lines
                ]
                
                if line_dicts:
                        # Используем statement, а не session.execute(insert(...)),
                        # чтобы SQLAlchemy мог работать с диалектом PostgreSQL.
                        stmt = pg_insert(DocumentLineORM).values(line_dicts)
                        await session.execute(stmt)
                    
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
                    .where(DocumentLineORM.doc_id == doc_id, DocumentLineORM.block_id == block_id)
                    .values(content=new_content)
                )
                await session.commit()
                return res.rowcount > 0
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to update line content for block {block_id}: {e}") from e
            
    async def copy_lines(self, source_doc_id: UUID, target_doc_id: UUID):
        """
        Копирует все строки из одного документа в другой с помощью SQL.
        """
        async for session in get_session(self._session_factory):
            try:
                # 1. Выбираем все строки-источники
                source_lines_stmt = select(DocumentLineORM).where(DocumentLineORM.doc_id == source_doc_id)
                source_lines = (await session.execute(source_lines_stmt)).scalars().all()

                if not source_lines:
                    return # Нечего копировать

                # 2. Готовим данные для вставки в новый документ
                new_lines_data = [
                    {
                        "doc_id": target_doc_id, # <-- Новый ID
                        "position": line.position,
                        "page_idx": line.page_idx,
                        "block_id": line.block_id,
                        "block_type": line.block_type,
                        "content": line.content,
                        "geometry": line.geometry,
                        "hierarchy": line.hierarchy,
                        "sheet_name": line.sheet_name
                    } for line in source_lines
                ]

                # 3. Вставляем скопом
                await session.execute(pg_insert(DocumentLineORM).values(new_lines_data))
                await session.commit()
                logger.info(f"Successfully copied {len(new_lines_data)} lines from doc {source_doc_id} to {target_doc_id}")
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to copy lines from {source_doc_id} to {target_doc_id}: {e}") from e
         
    async def get_lines_for_document(self, doc_id: UUID) -> List[DocumentLineORM]:
        """
        Возвращает список всех ORM-объектов строк для указанного документа.
        Строки отсортированы по их позиции в документе.
        """
        async for session in get_session(self._session_factory):
            stmt = (
                select(DocumentLineORM)
                .where(DocumentLineORM.doc_id == doc_id)
                .order_by(DocumentLineORM.position) # Сортировка важна для консистентности
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())
           
    async def list_all(self,
                       doc_id: UUID | None = None) -> list[Line]:
        """
        Если doc_id указан – возвращает строки только этого документа,
        иначе – все строки во всей базе.
        """
        async for session in get_session(self._session_factory):
            q = select(DocumentLineORM).order_by(
                DocumentLineORM.doc_id, DocumentLineORM.position
            )
            if doc_id:
                q = q.where(DocumentLineORM.doc_id == doc_id)

            rows = await session.execute(q)
            orms = rows.scalars().all()
            # ORM ➜ Pydantic (to_pydantic не был, конвертируем вручную)
            return [
                Line.model_validate(
                    {
                        "doc_id":       o.doc_id,
                        "block_id":     o.block_id,
                        "position":     o.position,
                        "type":         o.block_type,
                        "content":      o.content,
                    }
                )
                for o in orms
            ]