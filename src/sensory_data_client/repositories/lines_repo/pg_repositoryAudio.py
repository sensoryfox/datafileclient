from __future__ import annotations
from typing import List, Dict
from uuid import UUID
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from sensory_data_client.db.base import get_session
from sensory_data_client.db import RawLineORM
from sensory_data_client.db import AudioLineORM
from sensory_data_client.models.audio import AudioSentenceIn
from sensory_data_client.exceptions import DatabaseError

class AudioRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def replace_audio_sentences_with_meta(self, doc_id: UUID, sentences: List[AudioSentenceIn]) -> int:
        if not sentences:
            async with get_session(self._session_factory) as session:
                try:
                    await session.execute(delete(AudioLineORM).where(AudioLineORM.doc_id == doc_id))
                    await session.execute(
                        delete(RawLineORM).where(
                            (RawLineORM.doc_id == doc_id) & (RawLineORM.block_type.in_(("audio_sentence", "audio_segment")))
                        )
                    )
                    await session.commit()
                    return 0
                except SQLAlchemyError as e:
                    await session.rollback()
                    raise DatabaseError(f"Failed to clear audio sentences for {doc_id}: {e}") from e

        async with get_session(self._session_factory) as session:
            try:
                # 1) Удаляем старые аудио-мета и строки данного типа
                await session.execute(delete(AudioLineORM).where(AudioLineORM.doc_id == doc_id))
                await session.execute(
                    delete(RawLineORM).where(
                        (RawLineORM.doc_id == doc_id) & (RawLineORM.block_type.in_(("audio_sentence", "audio_segment")))
                    )
                )

                # 2) Вставляем строки-ядра и получаем (id, position)
                core_values = []
                for s in sentences:
                    core_values.append(
                        {
                            "doc_id": doc_id,
                            "position": int(s.position),
                            "block_type": "audio_sentence",
                            "content": s.text or "",
                        }
                    )
                stmt = pg_insert(RawLineORM).values(core_values).returning(RawLineORM.id, RawLineORM.position)
                res = await session.execute(stmt)
                inserted = res.fetchall()
                pos_to_id: Dict[int, UUID] = {row.position: row.id for row in inserted}

                # 3) Вставляем метаданные lines_audio
                meta_values = []
                for s in sentences:
                    lid = pos_to_id.get(int(s.position))
                    if not lid:
                        continue
                    dur = float(s.end_ts - s.start_ts)
                    meta_values.append(
                        {
                            "doc_id": doc_id,
                            "line_id": lid,
                            "start_ts": s.start_ts,
                            "end_ts": s.end_ts,
                            "duration": dur,
                            "speaker_label": s.speaker_label,
                            "speaker_idx": s.speaker_idx,
                            "emo_primary": s.emo_primary,
                            "emo_scores": s.emo_scores,
                            "tasks": s.tasks,
                            "confidence": s.confidence,
                        }
                    )
                if meta_values:
                    await session.execute(pg_insert(AudioLineORM).values(meta_values))

                await session.commit()
                return len(inserted)
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to save audio sentences for {doc_id}: {e}") from e

    # session-aware helpers
    async def bulk_insert_in_session(self, session: AsyncSession, values: List[Dict]):
        if not values:
            return
        await session.execute(pg_insert(AudioLineORM).values(values))