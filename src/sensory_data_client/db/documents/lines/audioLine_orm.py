from __future__ import annotations
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import String, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sensory_data_client.db.base import Base, CreatedAt

class AudioLineORM(Base):
    __tablename__ = "lines_audio"
    
    line_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("raw_lines.id", ondelete="CASCADE"), # Каскадное удаление
        primary_key=True
    )
    doc_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    start_ts: Mapped[float] = mapped_column(Float, nullable=False)
    end_ts:   Mapped[float] = mapped_column(Float, nullable=False)
    duration: Mapped[float] = mapped_column(Float, nullable=False)

    speaker_label: Mapped[str | None] = mapped_column(String, nullable=True)
    speaker_idx:   Mapped[int | None] = mapped_column(nullable=True)
    confidence:    Mapped[float | None] = mapped_column(Float, nullable=True)

    emo_primary:   Mapped[str | None] = mapped_column(String, nullable=True)
    emo_scores:    Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    tasks:         Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # например {"tasks":["transcribe","diarization","emotion"]}

    created_at: Mapped[CreatedAt] 

    line = relationship("RawLineORM", back_populates="audio_details")
    document: Mapped["DocumentORM"] = relationship(
        "DocumentORM",
        back_populates="audio_lines" # Указываем точное имя обратной связи из DocumentORM
    )
    
    __table_args__ = (
        Index("ix_audio_details_doc", "doc_id"),
        Index("ix_audio_details_speaker", "doc_id", "speaker_label"),
        Index("ix_audio_details_emo", "emo_scores"),
    )