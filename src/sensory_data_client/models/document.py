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
    owner: str
    access_group: Optional[str] = None
    extension: Optional[str] = None
    metadata: Optional[DocumentMetadata] = None

class DocumentInDB(DocumentCreate):
    id: UUID = Field(default_factory=uuid4)
    created: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    edited: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    content_hash: str
    object_path: str
    md_object_path: Optional[str] = None
