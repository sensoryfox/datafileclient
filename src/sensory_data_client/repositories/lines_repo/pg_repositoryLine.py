import logging
import re
from typing import List, Optional, Dict, Any
from collections import Counter
from uuid import UUID
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sensory_data_client.utils.cli_utils import parse_image_hash_from_md

from sensory_data_client.exceptions import DatabaseError
from sensory_data_client.models.line import Line, NormLine  # Pydantic-модель (минимальная)
from sensory_data_client.db.base import get_session
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

# ВАЖНО: проверьте корректность импортов ORM-классов под вашу структуру модулей
from sensory_data_client.db.documents.lines.rawline_orm import RawLineORM
from sensory_data_client.db.documents.lines.documentLine_orm import DocumentLineORM  # __tablename__="lines_document"
from sensory_data_client.db.documents.lines.imageLine_orm import ImageLineORM        # __tablename__="lines_image"
from sensory_data_client.db.documents.lines.audioLine_orm import AudioLineORM        # __tablename__="lines_audio"
from sensory_data_client.repositories import DocumentDetailsRepository
from sensory_data_client.repositories import ImageRepository
from sensory_data_client.repositories import AudioRepository
from sensory_data_client.db.uow import AsyncUnitOfWork
from sensory_data_client.db import DocType
logger = logging.getLogger(__name__)


class LineRepository:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        doc_repo: DocumentDetailsRepository,
        img_repo: ImageRepository,
        audio_repo: AudioRepository,
    ):
        self._session_factory = session_factory
        self._doc_repo = doc_repo
        self._img_repo = img_repo
        self._audio_repo = audio_repo

    @staticmethod
    def _is_image_block(block_type: str | None, obj: Any) -> bool:
        bt = str(block_type).lower()
        return bt in {"image", "image_placeholder", "img", "picture", "figure", "photo", "diagram"} or bool(getattr(obj, "is_image", False))

    # ------------- Вспомогательные методы классификации модальности -------------

    @staticmethod
    def _detect_block_type(obj: Any) -> Optional[str]:
        """
        Унифицирует чтение типа блока из pydantic-объекта/словаря.
        Допускаем, что поле может называться block_type или type.
        """
        bt = getattr(obj, "block_type", None)
        if bt:
            return bt
        # Pydantic Line мог называться 'type'
        return getattr(obj, "type", None)

    @staticmethod
    def _is_image_line(block_type: Optional[str], obj: Any) -> bool:
        if block_type is None:
            return False
        bt = str(block_type).lower()
        # Расширяемый список синонимов для изображений
        if bt in {"image", "image_placeholder", "img", "picture"}:
            return True
        # флаги из модели
        return bool(getattr(obj, "is_image", False))

    @staticmethod
    def _is_audio_line(block_type: Optional[str], obj: Any) -> bool:
        if block_type is None:
            # наличие тайм-кодов часто сигналит про аудио
            return any(hasattr(obj, x) for x in ("start_ts", "end_ts", "duration"))
        bt = str(block_type).lower()
        if bt in {"audio", "audio_sentence", "audio_segment"}:
            return True
        return any(hasattr(obj, x) for x in ("start_ts", "end_ts", "duration"))

    @staticmethod
    def _geometry_dict(obj: Any) -> Optional[dict]:
        """
        Унификация получения geometry: либо уже dict, либо собираем из polygon/bbox.
        """
        geom = getattr(obj, "geometry", None)
        if isinstance(geom, dict):
            return geom
        polygon = getattr(obj, "polygon", None) #TODO
        bbox = getattr(obj, "bbox", None)
        if polygon or bbox:
            return {"polygon": polygon, "bbox": bbox}
        return None

    # ------------- Основные public-методы (ИМЕНА СОХРАНЕНЫ) -------------
    async def save_lines(self, doc_id: UUID, lines: list[Line], doc_type: DocType):
        """
        Однократная запись массива строк для документа с маршрутизацией по DocType.

        Правила:
        - Повторный импорт строк для одного doc_id запрещен (если строки уже есть — ошибка).
        - Опираться только на position; проверяем уникальность позиций.
        - generic: разрешаем image-details (строки-плейсхолдеры); аудио пропускаем.
        - audio: изображения никогда не сохраняем; аудио-детали сохраняем только если есть start_ts.
        - video: как generic для изображений; аудио пока пропускаем.
        - Для изображений: если нет image_hash, пытаемся достать из ![](hash.png); без hash — строку изображения пропускаем.
        - Для изображений: в рамках одного вызова дедуп по line_id; безопасная вставка (on_conflict_do_nothing).
        """
        if not lines:
            return

        allow_images = doc_type in {DocType.generic, DocType.video}
        allow_audio = doc_type == DocType.audio

        # --------- ВНУТРЕННИЕ ХЕЛПЕРЫ (только для прозрачности логики) ---------

        def _validate_and_normalize_input(raw_lines: list[Any]) -> list[NormLine]:
            # Нормализуем вход в NormLine через Pydantic (валидаторы сработают автоматически)
            normalized: list[NormLine] = [NormLine.model_validate(ln) for ln in raw_lines]

            # проверим позиции
            positions = [int(n.position) for n in normalized]
            dups = [p for p, c in Counter(positions).items() if c > 1]
            if dups:
                raise DatabaseError(f"Duplicate positions in input: {dups[:10]}")
            return normalized

        def _geometry_dict(n: NormLine) -> Optional[dict]:
            if isinstance(n.geometry, dict):
                return n.geometry
            if n.polygon or n.bbox:
                return {"polygon": n.polygon, "bbox": n.bbox}
            return None

        def _build_core_values(nlines: list[NormLine]) -> list[dict]:
            return [
                {
                    "doc_id": doc_id,
                    "position": int(n.position),
                    "block_type": n.block_type or "text",
                    "content": n.content or "",
                }
                for n in nlines
            ]

        def _build_doc_details(nlines: list[NormLine], pos2id: dict[int, UUID]) -> list[dict]:
            values: list[dict] = []
            for n in nlines:
                g = _geometry_dict(n)
                if any(x is not None for x in (n.page_idx, n.block_id, g, n.hierarchy)):
                    values.append(
                        {
                            "line_id": pos2id[int(n.position)],
                            "doc_id": doc_id,
                            "page_idx": n.page_idx,
                            "block_id": n.block_id,
                            "geometry": g,
                            "hierarchy": n.hierarchy,
                            "attrs": n.attrs,
                        }
                    )
            return values

        def _build_image_details(nlines: list[NormLine], pos2id: dict[int, UUID]) -> list[dict]:
            if not allow_images:
                return []

            has_object_key_col = "object_key" in ImageLineORM.__table__.c.keys()
            values: list[dict] = []

            for n in nlines:
                if not n._is_image_block():
                    continue

                image_hash = n.image_hash or parse_image_hash_from_md(n.content)
                if not image_hash:
                    # нет hash – пропускаем, чтобы не падать на NOT NULL
                    continue

                row = {
                    "line_id": pos2id[int(n.position)],
                    "doc_id": doc_id,
                    "status": (n.status or "pending"),
                    "result_text": n.result_text,
                    "ocr_text": n.ocr_text,
                    "filename": (n.filename or f"{image_hash}.png"),
                    "image_hash": image_hash,
                }
                if has_object_key_col:
                    row["object_key"] = n.object_key
                values.append(row)

            # дедуп по line_id на всякий
            dedup: dict[UUID, dict] = {}
            for d in values:
                dedup[d["line_id"]] = d
            return list(dedup.values())

        def _build_audio_details(nlines: list[NormLine], pos2id: dict[int, UUID]) -> list[dict]:
            if not allow_audio:
                return []
            values: list[dict] = []
            for n in nlines:
                # Строго вставляем, только если есть start_ts (в БД NOT NULL)
                if n.start_ts is None:
                    continue
                values.append(
                    {
                        "line_id": pos2id[int(n.position)],
                        "doc_id": doc_id,
                        "start_ts": n.start_ts,
                        "end_ts": n.end_ts,
                        "duration": n.duration,
                        "speaker_label": n.speaker_label,
                        "speaker_idx": n.speaker_idx,
                        "confidence": n.confidence,
                        "emo_primary": n.emo_primary,
                        "emo_scores": n.emo_scores,
                    }
                )
            return values

        async def _insert_core(uow: AsyncUnitOfWork, core_vals: list[dict]) -> dict[int, UUID]:
            stmt = (
                pg_insert(RawLineORM)
                .values(core_vals)
                .returning(RawLineORM.id, RawLineORM.position)
            )
            res = await uow.session.execute(stmt)
            rows = res.fetchall()
            return {row.position: row.id for row in rows}

        async def _insert_doc_details(uow: AsyncUnitOfWork, values: list[dict]) -> None:
            if values:
                await self._doc_repo.bulk_insert_in_session(uow.session, values)

        async def _insert_image_details(uow: AsyncUnitOfWork, values: list[dict]) -> None:
            if not values:
                return
            stmt_img = (
                pg_insert(ImageLineORM)
                .values(values)
                .on_conflict_do_nothing(index_elements=[ImageLineORM.line_id])
            )
            await uow.session.execute(stmt_img)

        async def _insert_audio_details(uow: AsyncUnitOfWork, values: list[dict]) -> None:
            if values:
                await self._audio_repo.bulk_insert_in_session(uow.session, values)

        # ---------------------------
        # ОСНОВНОЙ ТРАНЗАКЦИОННЫЙ БЛОК
        # ---------------------------
        async with AsyncUnitOfWork(self._session_factory) as uow:
            try:
                # 0) Запрет на повторный импорт
                exists = await uow.session.scalar(
                    select(func.count()).select_from(RawLineORM).where(RawLineORM.doc_id == doc_id)
                )
                if exists and int(exists) > 0:
                    raise DatabaseError(
                        f"Document {doc_id} already has lines. Use update_lines()/copy_lines() instead of re-import."
                    )

                # 1) Валидация/нормализация входа
                nlines = _validate_and_normalize_input(lines)

                # 2) Вставка ядра
                core_vals = _build_core_values(nlines)
                pos2id = await _insert_core(uow, core_vals)

                # 3) Подготовка деталей
                doc_vals = _build_doc_details(nlines, pos2id)
                img_vals = _build_image_details(nlines, pos2id)
                audio_vals = _build_audio_details(nlines, pos2id)

                # 4) Запись деталей
                await _insert_doc_details(uow, doc_vals)
                await _insert_image_details(uow, img_vals)
                await _insert_audio_details(uow, audio_vals)

            except SQLAlchemyError as e:
                raise DatabaseError(f"Failed to save lines for document {doc_id}: {e}") from e

    async def update_lines(self, doc_id: UUID, block_id: str, new_content: str) -> bool:
        async with get_session(self._session_factory) as session:
            try:
                q_ids = (
                    select(RawLineORM.id)
                    .join(DocumentLineORM, DocumentLineORM.line_id == RawLineORM.id)
                    .where(RawLineORM.doc_id == doc_id, DocumentLineORM.block_id == block_id)
                )
                rows = await session.execute(q_ids)
                line_ids = [r[0] for r in rows.fetchall()]
                if not line_ids:
                    await session.rollback()
                    return False

                # upsert в lines_image
                img_rows = [
                    {"line_id": lid, "doc_id": doc_id, "status": "done", "result_text": new_content}
                    for lid in line_ids
                ]
                stmt_upsert_img = (
                    pg_insert(ImageLineORM)
                    .values(img_rows)
                    .on_conflict_do_update(
                        index_elements=[ImageLineORM.line_id],
                        set_={
                            "doc_id": doc_id,
                            "status": "done",
                            "result_text": new_content,
                        },
                    )
                )
                await session.execute(stmt_upsert_img)

                # обновим plain-текст ядра
                await session.execute(
                    update(RawLineORM)
                    .where(RawLineORM.id.in_(line_ids))
                    .values(content=new_content)
                )

                await session.commit()
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to update image alt-text for block {block_id}: {e}") from e

    async def copy_lines(self, source_doc_id: UUID, target_doc_id: UUID):
        async with get_session(self._session_factory) as session:
            try:
                src_stmt = (
                    select(RawLineORM)
                    .where(RawLineORM.doc_id == source_doc_id)
                    .order_by(RawLineORM.position)
                )
                src_core = (await session.execute(src_stmt)).scalars().all()
                if not src_core:
                    return

                core_values = [
                    {
                        "doc_id": target_doc_id,
                        "position": r.position,
                        "block_type": r.block_type,
                        "content": r.content,
                    }
                    for r in src_core
                ]
                insert_target = (
                    pg_insert(RawLineORM)
                    .values(core_values)
                    .returning(RawLineORM.id, RawLineORM.position)
                )
                inserted = (await session.execute(insert_target)).fetchall()
                pos2newid = {row.position: row.id for row in inserted}
                if not pos2newid:
                    await session.rollback()
                    raise DatabaseError("copy_lines: failed to insert target core rows")

                # lines_document
                src_doc_d = (
                    select(DocumentLineORM, RawLineORM.position)
                    .join(RawLineORM, RawLineORM.id == DocumentLineORM.line_id)
                    .where(RawLineORM.doc_id == source_doc_id)
                    .order_by(RawLineORM.position)
                )
                doc_rows = (await session.execute(src_doc_d)).all()
                if doc_rows:
                    doc_values = []
                    for d, pos in doc_rows:
                        new_line_id = pos2newid.get(pos)
                        if not new_line_id:
                            continue
                        doc_values.append(
                            {
                                "line_id": new_line_id,
                                "doc_id": target_doc_id,
                                "page_idx": d.page_idx,
                                "block_id": d.block_id,
                                "geometry": d.geometry,
                                "hierarchy": d.hierarchy,
                                "attrs": d.attrs,
                            }
                        )
                    if doc_values:
                        await session.execute(pg_insert(DocumentLineORM).values(doc_values))

                # lines_image
                src_img_d = (
                    select(ImageLineORM, RawLineORM.position)
                    .join(RawLineORM, RawLineORM.id == ImageLineORM.line_id)
                    .where(RawLineORM.doc_id == source_doc_id)
                )
                img_rows = (await session.execute(src_img_d)).all()
                if img_rows:
                    img_values = []
                    for img, pos in img_rows:
                        new_line_id = pos2newid.get(pos)
                        if not new_line_id:
                            continue
                        img_values.append(
                            {
                                "line_id": new_line_id,
                                "doc_id": target_doc_id,
                                "status": img.status,
                                "result_text": img.result_text,
                                "ocr_text": img.ocr_text,
                                "filename": img.filename,
                                "image_hash": img.image_hash,
                            }
                        )
                    if img_values:
                        await session.execute(pg_insert(ImageLineORM).values(img_values))

                # lines_audio
                src_audio_d = (
                    select(AudioLineORM, RawLineORM.position)
                    .join(RawLineORM, RawLineORM.id == AudioLineORM.line_id)
                    .where(RawLineORM.doc_id == source_doc_id)
                )
                audio_rows = (await session.execute(src_audio_d)).all()
                if audio_rows:
                    audio_values = []
                    for a, pos in audio_rows:
                        new_line_id = pos2newid.get(pos)
                        if not new_line_id:
                            continue
                        audio_values.append(
                            {
                                "line_id": new_line_id,
                                "doc_id": target_doc_id,
                                "start_ts": a.start_ts,
                                "end_ts": a.end_ts,
                                "duration": a.duration,
                                "speaker_label": a.speaker_label,
                                "speaker_idx": a.speaker_idx,
                                "confidence": a.confidence,
                                "emo_primary": a.emo_primary,
                                "emo_scores": a.emo_scores,
                            }
                        )
                    if audio_values:
                        await session.execute(pg_insert(AudioLineORM).values(audio_values))

                await session.commit()
                logger.info("Successfully copied %d lines from %s to %s", len(src_core), str(source_doc_id), str(target_doc_id))
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"Failed to copy lines: {e}") from e

    async def get_lines_for_document(self, doc_id: UUID) -> List[RawLineORM]:
        async with get_session(self._session_factory) as session:
            stmt = (
                select(RawLineORM)
                .where(RawLineORM.doc_id == doc_id)
                .order_by(RawLineORM.position)
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def list_all(self, doc_id: UUID | None = None) -> list[Line]:
        async with get_session(self._session_factory) as session:
            q = select(RawLineORM)
            if doc_id:
                q = q.where(RawLineORM.doc_id == doc_id).order_by(RawLineORM.position)
            else:
                q = q.order_by(RawLineORM.doc_id, RawLineORM.position)
            rows = (await session.execute(q)).scalars().all()
            return [
                Line.model_validate(
                    {
                        "doc_id":       o.doc_id,
                        "block_id":     None,
                        "position":     o.position,
                        "type":         o.block_type,
                        "content":      o.content,
                    }
                )
                for o in rows
            ]

    async def get_line_core(self, line_id: UUID) -> Optional[RawLineORM]:
        async with get_session(self._session_factory) as session:
            stmt = select(RawLineORM).where(RawLineORM.id == line_id)
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def get_lines_for_document_joined(self, doc_id: UUID) -> list[dict]:
        async with get_session(self._session_factory) as session:
            stmt = (
                select(RawLineORM, DocumentLineORM, ImageLineORM, AudioLineORM)
                .join(DocumentLineORM, DocumentLineORM.line_id == RawLineORM.id, isouter=True)
                .join(ImageLineORM, ImageLineORM.line_id == RawLineORM.id, isouter=True)
                .join(AudioLineORM, AudioLineORM.line_id == RawLineORM.id, isouter=True)
                .where(RawLineORM.doc_id == doc_id)
                .order_by(RawLineORM.position)
            )
            rows = (await session.execute(stmt)).all()

            enriched: list[dict] = []
            for raw, docd, imgd, audd in rows:
                enriched.append(
                    {
                        "line_id": str(raw.id),
                        "doc_id": str(raw.doc_id),
                        "position": raw.position,
                        "block_type": raw.block_type,
                        "content": raw.content,
                        "created_at": raw.created_at,

                        "page_idx": getattr(docd, "page_idx", None),
                        "block_id": getattr(docd, "block_id", None),
                        "geometry": getattr(docd, "geometry", None),
                        "hierarchy": getattr(docd, "hierarchy", None),
                        "attrs": getattr(docd, "attrs", None),

                        "image_status": getattr(imgd, "status", None),
                        "image_text": getattr(imgd, "result_text", None),
                        "image_ocr_text": getattr(imgd, "ocr_text", None),

                        "start_ts": getattr(audd, "start_ts", None),
                        "end_ts": getattr(audd, "end_ts", None),
                        "duration": getattr(audd, "duration", None),
                        "speaker_label": getattr(audd, "speaker_label", None),
                        "speaker_idx": getattr(audd, "speaker_idx", None),
                        "confidence": getattr(audd, "confidence", None),
                        "emo_primary": getattr(audd, "emo_primary", None),
                        "emo_scores": getattr(audd, "emo_scores", None),
                    }
                )
  
    async def upsert_image_result(self, line_id: UUID, doc_id: UUID, status: str, result_text: Optional[str]) -> bool:
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    pg_insert(ImageLineORM)
                    .values(
                        {
                            "line_id": line_id,
                            "doc_id": doc_id,
                            "status": status,
                            "result_text": result_text,
                        }
                    )
                    .on_conflict_do_update(
                        index_elements=[ImageLineORM.line_id],
                        set_={"doc_id": doc_id, "status": status, "result_text": result_text},
                    )
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except SQLAlchemyError as e:
                await session.rollback()
                raise DatabaseError(f"upsert_image_result failed for line {line_id}: {e}") from e
            
            
    async def get_text_contents(self, doc_id: UUID) -> List[str]:
        """Вернуть текст строк документа без картинок, только content, отсортировано по position."""
        async with get_session(self._session_factory) as session:
            try:
                stmt = (
                    select(RawLineORM.content)
                    .where(
                        RawLineORM.doc_id == doc_id,
                        RawLineORM.block_type.notin_(("image", "image_placeholder")),
                    )
                    .order_by(RawLineORM.position.asc())
                )
                res = await session.execute(stmt)
                items = [ (c or "").strip() for c in res.scalars().all() or [] ]
                return [c for c in items if c]
            except SQLAlchemyError as e:
                logger.error("get_text_contents failed for %s: %s", doc_id, e)
                return []