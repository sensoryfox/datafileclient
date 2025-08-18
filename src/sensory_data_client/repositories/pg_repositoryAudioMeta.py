import logging
from typing import List, Dict
from uuid import UUID
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from sensory_data_client.db.base import get_session
from sensory_data_client.db.documents.documentLine_orm import DocumentLineORM
from sensory_data_client.db.documents.audioLine_orm import AudioSentenceMetaORM
from sensory_data_client.models.audio import AudioSentenceIn
from sensory_data_client.exceptions import DatabaseError

logger = logging.getLogger(__name__)

class AudioRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def replace_audio_sentences_with_meta(self, doc_id: UUID, sentences: List[AudioSentenceIn]) -> int:
        """
        Полностью заменяет (перезаписывает) строки типа 'audio_sentence' для документа
        и соответствующие метаданные. Делает это в одной транзакции.

        Возвращает количество вставленных предложений.
        """
        if not sentences:
            # Очистить при пустом списке
            async for session in get_session(self._session_factory):
                try:
                    await session.execute(
                        delete(AudioSentenceMetaORM).where(AudioSentenceMetaORM.doc_id == doc_id)
                    )
                    await session.execute(
                        delete(DocumentLineORM).where(
                            DocumentLineORM.doc_id == doc_id,
                            DocumentLineORM.block_type == "audio_sentence"
                        )
                    )
                    await session.commit()
                    return 0
                except SQLAlchemyError as e:
                    await session.rollback()
                    raise DatabaseError(f"Failed to clear audio sentences for {doc_id}: {e}") from e

        async for session in get_session(self._session_factory):
            try:
                # 1) Удаляем старые метаданные и строки данного типа
                await session.execute(
                    delete(AudioSentenceMetaORM).where(AudioSentenceMetaORM.doc_id == doc_id)
                )
                await session.execute(
                    delete(DocumentLineORM).where(
                        DocumentLineORM.doc_id == doc_id,
                        DocumentLineORM.block_type == "audio_sentence"
                    )
                )

                # 2) Вставляем новые строки и получаем (id, position)
                line_dicts = []
                for s in sentences:
                    line_dicts.append({
                        "doc_id": doc_id,
                        "position": s.position,
                        "page_idx": None,
                        "block_id": f"aud-{s.position:06d}",
                        "block_type": "audio_sentence",
                        "content": s.text,
                        "geometry": None,
                        "hierarchy": None,
                        "sheet_name": None
                    })

                stmt = pg_insert(DocumentLineORM).values(line_dicts).returning(
                    DocumentLineORM.id, DocumentLineORM.position
                )
                res = await session.execute(stmt)
                inserted = res.fetchall()  # list[Row]
                # map pos -> line_id
                pos_to_id: Dict[int, UUID] = {row.position: row.id for row in inserted}

                # 3) Вставляем метаданные с привязкой к line_id
                meta_dicts = []
                for s in sentences:
                    lid = pos_to_id.get(s.position)
                    if not lid:
                        continue
                    dur = float(s.end_ts - s.start_ts)
                    meta_dicts.append({
                        "doc_id": doc_id,
                        "line_id": lid,
                        "start_ts": s.start_ts,
                        "end_ts": s.end_ts,
                        "duration": dur,
                        "speaker_label": s.speaker_label,
                        "speaker_idx": s.speaker_idx,
                        "confidence": s.confidence,
                        "emo_primary": s.emo_primary,
                        "emo_scores": s.emo_scores,
                        "tasks": s.tasks,
                    })

                if meta_dicts:
                    await session.execute(pg_insert(AudioSentenceMetaORM).values(meta_dicts))

                await session.commit()
                return len(inserted)
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to save audio sentences for {doc_id}: {e}") from e