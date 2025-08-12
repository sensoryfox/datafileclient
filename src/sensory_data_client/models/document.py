from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

class DocumentMetadata(BaseModel):
    processing_status: Optional[str] = None
    image_object_paths: Optional[List[str]] = None
    extra: Optional[dict] = None

class DocumentCreate(BaseModel):
    user_document_id: str
    name: str
    owner_id: str
    access_group_id: Optional[str] = None
    metadata: Optional[DocumentMetadata] = None

class DocumentInDB(DocumentCreate):
    id: UUID = Field(default_factory=uuid4)
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    edited: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    # Поля из связанной таблицы stored_files
    extension: str
    content_hash: str
    object_path: str

    class Config:
        orm_mode = True 