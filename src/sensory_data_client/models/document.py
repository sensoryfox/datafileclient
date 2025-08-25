from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field
from .group import GroupInDB
class DocumentMetadata(BaseModel):
    size_bytes: Optional[int] = None
    language: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

class DocumentCreate(BaseModel):
    name: str
    user_document_id: Optional[str] = None
    owner_id: UUID
    access_group_id: Optional[UUID] = None
    is_public: bool = False
    metadata: Optional[DocumentMetadata] = None

class DocumentInDB(DocumentCreate):
    id: UUID = Field(default_factory=uuid4)
    access_group: Optional[GroupInDB] = None
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    edited: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    # Поля из связанной таблицы stored_files
    is_sync_enabled: bool
    is_public: bool
    doc_type: str
    extension: str
    content_hash: str
    object_path: str

    class Config:
        from_attributes = True 