import logging
import hashlib
import os
from uuid import UUID, uuid4

from sensory_data_client.repositories.pg_repositoryMeta import MetaDataRepository
from sensory_data_client.repositories.pg_repositoryLine import LineRepository
from sensory_data_client.repositories.minio_repository import MinioRepository
from sensory_data_client.repositories.pg_repositoryObj import ObjectRepository
from sensory_data_client.db import DocumentORM, StoredFileORM
from sensory_data_client.models.document import DocumentCreate, DocumentInDB
from sensory_data_client.models.line import Line
from sensory_data_client.exceptions import DocumentNotFoundError, DatabaseError, MinioError

from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
logger = logging.getLogger(__name__)

class DataClient:
    """
    Единая точка доступа для бизнес-логики.
    """

    def __init__(self, meta_repo: MetaDataRepository | None = None, line_repo: LineRepository | None = None, 
                 minio_repo: MinioRepository | None = None, obj_repo: ObjectRepository | None = None):
        self.metarepo = meta_repo
        self.linerepo = line_repo
        self.minio = minio_repo
        self.obj = obj_repo

    async def check_connections(self) -> dict[str, str]:
        """
        Проверяет доступность всех внешних сервисов (PostgreSQL, MinIO).
        Возвращает словарь со статусами.
        """
        statuses = {}
        
        # PostgreSQL Check
        try:
            await self.metarepo.check_connection()
            statuses["postgres"] = "ok"
        except DatabaseError as e:
            statuses["postgres"] = f"failed: {e}"
            
        # MinIO Check
        try:
            await self.minio.check_connection()
            statuses["minio"] = "ok"
        except MinioError as e:
            statuses["minio"] = f"failed: {e}"
            
        return statuses
    
    
    async def put_object(self, object_name: str, data: bytes, content_type: str | None = None):
        """Универсальный метод для загрузки объекта в MinIO."""
        await self.minio.put_object(object_name, data, content_type)

    async def get_object(self, object_name: str) -> bytes:
        """Универсальный метод для скачивания объекта из MinIO."""
        return await self.minio.get_object(object_name)
    
    # ――― atomic high-level ops ――― #
    

    async def upload_file(self, file_name: str, content: bytes, meta: DocumentCreate) -> DocumentInDB:
        """
        Загружает файл, применяя дедупликацию по хэшу контента.
        
        - Если файл с таким же хэшем уже существует, новый файл в MinIO не загружается.
          Создается только новая запись в 'documents', ссылающаяся на существующий 'stored_files'.
        - Если файл новый, он загружается в MinIO, и в БД создаются обе записи
          ('stored_files' и 'documents') в рамках одной транзакции.
        """
        # 1. Считаем хэш и ищем существующий физический файл
        content_hash = hashlib.sha256(content).hexdigest()
        logger.info(f"Uploading file '{file_name}' with hash {content_hash[:8]}...")
        
        existing_stored_file = await self.metarepo.get_stored_file_by_hash(content_hash)
        
        # --- Сценарий A: Файл с таким контентом уже существует ---
        if existing_stored_file:
            logger.info(f"Duplicate content detected. Linking to existing file ID {existing_stored_file.id}")
            
            # Создаем только логическую запись о документе
            document_orm = DocumentORM(
                **meta.model_dump(),
                id=uuid4(),
                stored_file_hash=existing_stored_file.content_hash  # Ссылка на существующий файл!
            )
            
            # Сохраняем ТОЛЬКО метаданные. Транзакция не нужна, т.к. операция одна.
            saved_doc_orm = await self.metarepo.save(document_orm)
            # Необходимо обогатить pydantic модель данными из связанной таблицы
            return document_orm.to_pydantic()

        # --- Сценарий Б: Это новый, уникальный файл ---
        else:
            logger.info("New unique content. Uploading to MinIO and creating new DB entries.")
            object_path = self._build_object_path(file_name, uuid4())

            try:
                # Шаг 1: Загружаем в MinIO
                await self.minio.put_object(object_path, content, content_type="application/octet-stream")

                # Шаг 2: Готовим ORM-объекты для обеих таблиц
                stored_file_orm = StoredFileORM(
                    content_hash=content_hash,
                    object_path=object_path,
                    size_bytes=len(content)
                )
                
                document_orm = DocumentORM(
                    **meta.model_dump(),
                    id=uuid4(),
                    stored_file=stored_file_orm
                )

                # Шаг 3: Сохраняем оба объекта в одной транзакции
                await self.metarepo.save_new_physical_file(stored_file_orm, document_orm)
                
                # Возвращаем полную Pydantic модель
                return document_orm.to_pydantic()

            except (DatabaseError, MinioError) as e:
                logger.error(f"Transaction failed during new file upload: {e}. Rolling back MinIO upload.")
                # Rollback: если запись в БД не удалась, удаляем уже загруженный файл из MinIO
                await self.minio.remove_object(object_path)
                raise  # Перевыбрасываем исключение наверх
    
    async def get_file(self, doc_id: UUID) -> bytes:
        doc = await self.metarepo.get(doc_id)
        if not doc:
            raise DocumentNotFoundError
        return await self.minio.get_object(doc.object_path)

    async def delete_file(self, doc_id: UUID):
        doc = await self.metarepo.get(doc_id)
        if not doc:
            raise DocumentNotFoundError
        await self.minio.remove_object(doc.object_path)
        await self.metarepo.delete(doc_id)
    
    async def generate_download_url(self, doc_id: UUID, expires_in: int = 3600) -> str:
        """
        Создает временную ссылку для скачивания файла, связанного с документом.
        """
        doc = await self.metarepo.get(doc_id)
        if not doc:
            raise DocumentNotFoundError(f"Document with id {doc_id} not found.")
        
        url = await self.minio.get_presigned_url(doc.object_path, expires_in_seconds=expires_in)
        logger.info(f"Generated presigned URL for document {doc_id}")
        return url
    
    async def save_document_lines(self, doc_id: UUID, lines: list[Line]):
        """Сохраняет разобранные строки документа в PostgreSQL."""
        logger.info(f"Saving {len(lines)} lines for document {doc_id}")
        await self.linerepo.save_lines(doc_id, lines)    
    
    async def update_lines(self, doc_id: UUID, block_id: str, new_content: str):
        """Обновляет markdown-строку, добавляя описание изображения."""
        logger.info(f"Updating alt text for block {block_id} in document {doc_id}")
        await self.linerepo.update_lines(doc_id, block_id, new_content)
        
    # ――― helpers ――― #
    @staticmethod
    def _build_object_path(fname: str, doc_id: UUID) -> str:
        base, ext = os.path.splitext(fname)
        ext = ext.lstrip(".") or "bin"
        return f"{ext}/{doc_id.hex}/{fname}"

    async def list_doc(self,
                             limit: int | None = None,
                             offset: int = 0):
        return await self.metarepo.list_all(limit, offset)

    async def list_doclines(self,
                                  doc_id: UUID | None = None):
        return await self.linerepo.list_all(doc_id)

    async def list_stor(self,
                                   prefix: str | None = None,
                                   recursive: bool = True):
        return await self.minio.list_all(prefix, recursive)
    
    async def list_stored_files(self,
                                   limit: int | None = None,
                                   offset: int = 0):
        """Возвращает список всех физически сохраненных файлов."""
        return await self.obj.list_all(limit, offset)