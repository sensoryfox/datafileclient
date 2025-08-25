# sensory_data_client/repositories/autotag_repo.py
from __future__ import annotations

from typing import Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from sensory_data_client.db.base import get_session
from sensory_data_client.db.tags.autotag_task_orm import AutotagTaskORM


class AutotagRepository:
    """
    Репозиторий задач автотегирования.

    Статусы:
      - enqueued   — задача ожидает обработки (только при создании или ручном возврате в очередь)
      - processing — в обработке; при бэкоффах статус НЕ меняем на enqueued, чтобы не триггерить NOTIFY
      - done       — завершена
      - failed     — завершилась ошибкой
    """

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get_by_id(self, task_id: UUID) -> Optional[AutotagTaskORM]:
        async with get_session(self._session_factory) as session:
            res = await session.execute(
                select(AutotagTaskORM).where(AutotagTaskORM.id == task_id).limit(1)
            )
            return res.scalar_one_or_none()

    async def create_or_get_pending(self, doc_id: UUID, llm_model: str | None = None) -> AutotagTaskORM:
        """
        Идемпотентно создает задачу, если отсутствует активная (enqueued/processing), либо возвращает активную.
        """
        async with get_session(self._session_factory) as session:
            # Ищем активную
            q = (
                select(AutotagTaskORM)
                .where(
                    AutotagTaskORM.doc_id == doc_id,
                    AutotagTaskORM.status.in_(["enqueued", "processing"]),
                )
                .limit(1)
            )
            res = await session.execute(q)
            existing = res.scalar_one_or_none()
            if existing:
                return existing

            # Создаем новую со статусом enqueued
            task = AutotagTaskORM(doc_id=doc_id, llm_model=llm_model)
            session.add(task)
            await session.commit()
            await session.refresh(task)
            return task

    async def lock_for_processing(self, task_id: UUID) -> Optional[AutotagTaskORM]:
        """
        Захват задачи в обработку: статус -> 'processing', attempts += 1.
        Важно: разрешаем захватывать и когда статус уже 'processing' (для повторов с бэкоффом).
        """
        async with get_session(self._session_factory) as session:
            stmt = (
                update(AutotagTaskORM)
                .where(
                    AutotagTaskORM.id == task_id,
                    AutotagTaskORM.status.in_(["enqueued", "processing"]),
                )
                .values(
                    status="processing",
                    attempts=AutotagTaskORM.attempts + 1,
                    updated_at=func.now(),
                )
                .returning(AutotagTaskORM)
            )
            res = await session.execute(stmt)
            task = res.scalar_one_or_none()
            await session.commit()
            return task

    async def update_error(self, task_id: UUID, error: str) -> None:
        """
        Записать last_error. Статус не меняется.
        """
        async with get_session(self._session_factory) as session:
            await session.execute(
                update(AutotagTaskORM)
                .where(AutotagTaskORM.id == task_id)
                .values(last_error=error, updated_at=func.now())
            )
            await session.commit()

    async def mark_done(self, task_id: UUID, result_json: dict | None = None) -> None:
        async with get_session(self._session_factory) as session:
            await session.execute(
                update(AutotagTaskORM)
                .where(AutotagTaskORM.id == task_id)
                .values(
                    status="done",
                    result_json=result_json,
                    processed_at=func.now(),
                    updated_at=func.now(),
                )
            )
            await session.commit()

    async def mark_failed(self, task_id: UUID, reason: str) -> None:
        async with get_session(self._session_factory) as session:
            await session.execute(
                update(AutotagTaskORM)
                .where(AutotagTaskORM.id == task_id)
                .values(
                    status="failed",
                    last_error=reason,
                    processed_at=func.now(),
                    updated_at=func.now(),
                )
            )
            await session.commit()