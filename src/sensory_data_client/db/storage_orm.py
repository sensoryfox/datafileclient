# В новом файле, например, db/storage_orm.py
from sqlalchemy import String, BigInteger, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime

from .base import Base

class StoredFileORM(Base):
    __tablename__ = "stored_files"

    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    object_path: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )