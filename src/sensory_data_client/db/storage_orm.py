# В новом файле, например, db/storage_orm.py
from sqlalchemy import String, BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from .base import Base

class StoredFileORM(Base):
    __tablename__ = "stored_files"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    object_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extension: Mapped[str | None] = mapped_column(String, nullable=True)
    first_uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    