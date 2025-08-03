import logging
import hashlib
import os
from uuid import UUID, uuid4

from .repositories.pg_repository import PostgresRepository
from .repositories.minio_repository import MinioRepository
from .models.document import DocumentCreate, DocumentInDB, Line
from .exceptions import DocumentNotFoundError, DatabaseError, MinioError

logger = logging.getLogger(__name__)


class DataClient:
    """
    Единая точка доступа для бизнес-логики.
    """

    def __init__(self, pg_repo: PostgresRepository | None = None, minio_repo: MinioRepository | None = None):
        self.pg = pg_repo or PostgresRepository()
        self.minio = minio_repo or MinioRepository()


    async def put_object(self, object_name: str, data: bytes, content_type: str | None = None):
        """Универсальный метод для загрузки объекта в MinIO."""
        await self.minio.put_object(object_name, data, content_type)

    async def get_object(self, object_name: str) -> bytes:
        """Универсальный метод для скачивания объекта из MinIO."""
        return await self.minio.get_object(object_name)
    
    # ――― atomic high-level ops ――― #
    
    async def upload_file(self, file_name: str, content: bytes, meta: DocumentCreate) -> DocumentInDB:
        document_uuid = uuid4()
        object_path = self._build_object_path(file_name, document_uuid)
        content_hash = hashlib.sha256(content).hexdigest()

        # 1. MinIO ➜ если упадёт – исключение, в БД ничего не пишем
        await self.minio.put_object(object_path, content, content_type="application/octet-stream")

        # 2. БД
        doc_in_db = DocumentInDB(
            **meta.model_dump(),
            id=document_uuid,
            content_hash=content_hash,
            object_path=object_path,
            md_object_path=None,
        )
        try:
            saved = await self.pg.save(doc_in_db)
            return saved
        except DatabaseError as e:
            # Rollback: удаляем из MinIO
            await self.minio.remove_object(object_path)
            raise
    
    async def get_file(self, doc_id: UUID) -> bytes:
        doc = await self.pg.get(doc_id)
        if not doc:
            raise DocumentNotFoundError
        return await self.minio.get_object(doc.object_path)

    async def delete_file(self, doc_id: UUID):
        doc = await self.pg.get(doc_id)
        if not doc:
            raise DocumentNotFoundError
        await self.minio.remove_object(doc.object_path)
        await self.pg.delete(doc_id)
    
    async def generate_download_url(self, doc_id: UUID, expires_in: int = 3600) -> str:
        """
        Создает временную ссылку для скачивания файла, связанного с документом.
        """
        doc = await self.pg.get(doc_id)
        if not doc:
            raise DocumentNotFoundError(f"Document with id {doc_id} not found.")
        
        url = await self.minio.get_presigned_url(doc.object_path, expires_in_seconds=expires_in)
        logger.info(f"Generated presigned URL for document {doc_id}")
        return url
    
    async def save_document_lines(self, doc_id: UUID, lines: list[Line]):
        """Сохраняет разобранные строки документа в PostgreSQL."""
        logger.info(f"Saving {len(lines)} lines for document {doc_id}")
        await self.pg.save_lines(doc_id, lines)    
    
    async def update_lines(self, doc_id: UUID, block_id: str, new_content: str):
        """Обновляет markdown-строку, добавляя описание изображения."""
        logger.info(f"Updating alt text for block {block_id} in document {doc_id}")
        await self.pg.update_lines(doc_id, block_id, new_content)
        
    # ――― helpers ――― #
    @staticmethod
    def _build_object_path(fname: str, doc_id: UUID) -> str:
        base, ext = os.path.splitext(fname)
        ext = ext.lstrip(".") or "bin"
        return f"{ext}/{doc_id.hex}-{fname}"