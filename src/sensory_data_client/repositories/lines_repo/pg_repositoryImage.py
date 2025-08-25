from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sensory_data_client.db.base import get_session
from sensory_data_client.db import ImageLineORM
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

class ImageRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    # СОВМЕСТИМО СТАРЫМ ИНТЕРФЕЙСОМ: создаёт/обновляет запись в lines_image для source_line_id
    async def create_task(
        self,
        doc_id: UUID,
        filename: str,
        image_hash: str,
        source_line_id: Optional[UUID] = None
    ) -> UUID:
        if not source_line_id:
            raise DatabaseError("create_task requires source_line_id (line_id in raw_lines)")

        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    pg_insert(ImageLineORM)
                    .values(
                        {
                            "line_id": source_line_id,
                            "doc_id": doc_id,
                            "filename": filename,
                            "image_hash": image_hash,
                            "status": "pending",
                            "attempts": 0,
                        }
                    )
                    .on_conflict_do_update(
                        index_elements=[ImageLineORM.line_id],
                        set_={
                            "doc_id": doc_id,
                            "filename": filename,
                            "image_hash": image_hash,
                            "status": "pending",
                            "attempts": 0,
                            "updated_at": datetime.utcnow(),
                        },
                    )
                    .returning(ImageLineORM.line_id)
                )
                res = await session.execute(stmt)
                await session.commit()
                return res.scalar_one()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error("Failed to create image task: %s", e)
                raise DatabaseError(f"Failed to create image task: {e}") from e

    async def claim_task(self, image_id: UUID) -> Optional[ImageLineORM]:
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    update(ImageLineORM)
                    .where(
                        ImageLineORM.line_id == image_id,
                        ImageLineORM.status.in_(("pending", "enqueued"))
                    )
                    .values(
                        status="processing",
                        attempts=ImageLineORM.attempts + 1,
                        updated_at=datetime.now()
                    )
                    .returning(ImageLineORM)
                )
                res = await session.execute(stmt)
                await session.commit()
                return res.scalar_one_or_none()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error("Failed to claim image task %s: %s", str(image_id), e)
                raise DatabaseError(f"Failed to claim image task {image_id}: {e}") from e

    async def update_task_status(
        self,
        image_id: UUID,
        status: str,
        result_text: Optional[str] = None,
        last_error: Optional[str] = None,
        llm_model: Optional[str] = None,
        ocr_text: Optional[str] = None,
    ):
        values: Dict[str, Any] = {"status": status, "updated_at": datetime.utcnow()}
        if result_text is not None:
            values["result_text"] = result_text
        if last_error is not None:
            values["last_error"] = last_error
        if llm_model is not None:
            values["llm_model"] = llm_model
        if ocr_text is not None:
            values["ocr_text"] = ocr_text
        if status == "done":
            values["processed_at"] = datetime.utcnow()
            values["last_error"] = None

        async with get_session(self._session_factory) as session:
            try:
                stmt = update(ImageLineORM).where(ImageLineORM.line_id == image_id).values(**values)
                await session.execute(stmt)
                await session.commit()
            except SQLAlchemyError as e:
                await session.rollback()
                logger.error("Failed to update status for image task %s: %s", str(image_id), e)
                raise DatabaseError(f"Failed to update status for image task {image_id}: {e}") from e

    async def find_stalled_tasks(self, threshold_minutes: int) -> list[ImageLineORM]:
        stalled_since = datetime.utcnow() - timedelta(minutes=threshold_minutes)
        async with get_session(self._session_factory) as session:
            stmt = select(ImageLineORM).where(
                ImageLineORM.status.in_(("enqueued", "processing")),
                ImageLineORM.updated_at < stalled_since
            )
            res = await session.execute(stmt)
            return list(res.scalars().all())

    async def get_description_by_line_id(self, source_line_id: UUID) -> Optional[str]:
        async with get_session(self._session_factory) as session:
            stmt = (
                select(ImageLineORM.result_text)
                .where(
                    ImageLineORM.line_id == source_line_id,
                    ImageLineORM.status == "done"
                )
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def get_images_by_doc_id(self, doc_id: UUID) -> List[ImageLineORM]:
        async with get_session(self._session_factory) as session:
            stmt = select(ImageLineORM).where(ImageLineORM.doc_id == doc_id).order_by(ImageLineORM.created_at)
            res = await session.execute(stmt)
            return list(res.scalars().all())

    # session-aware helpers (универсальные низкоуровневые)
    async def upsert_in_session(self, session: AsyncSession, values: Dict[str, Any]):
        stmt = (
            pg_insert(ImageLineORM)
            .values(values)
            .on_conflict_do_update(
                index_elements=[ImageLineORM.line_id],
                set_=values
            )
        )
        await session.execute(stmt)

    async def bulk_insert_in_session(self, session: AsyncSession, values: List[Dict[str, Any]]):
        if not values:
            return
        await session.execute(pg_insert(ImageLineORM).values(values))