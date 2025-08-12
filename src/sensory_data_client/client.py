import logging
import hashlib
import os
from uuid import UUID, uuid4
from typing import Optional
from pathlib import Path
from sensory_data_client.repositories import (MetaDataRepository, 
                                            ImageRepository, 
                                            LineRepository,
                                            MinioRepository,
                                            ObjectRepository)

from sensory_data_client.db import DocumentORM, StoredFileORM, DocumentImageORM, UserORM
from sensory_data_client.models import Line, DocumentCreate, DocumentInDB
from sensory_data_client.exceptions import DocumentNotFoundError, DatabaseError, MinioError

logger = logging.getLogger(__name__)

class DataClient:
    """
    Единая точка доступа для бизнес-логики.
    """

    def __init__(
        self,
        meta_repo: MetaDataRepository | None = None,
        line_repo: LineRepository | None = None,
        minio_repo: MinioRepository | None = None,
        obj_repo: ObjectRepository | None = None,
        image_repo: ImageRepository | None = None,  # <-- ДОБАВИТЬ
    ):        
        self.metarepo = meta_repo
        self.linerepo = line_repo
        self.minio = minio_repo
        self.obj = obj_repo
        self.imagerepo = image_repo

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
        id_doc = uuid4()
        content_hash = hashlib.sha256(content).hexdigest()
        logger.info(f"Uploading file '{file_name}' with hash {content_hash[:8]}...")
        
        existing = await self.metarepo.get_stored_file_by_hash(content_hash)
        
        # --- Сценарий A: Файл с таким контентом уже существует ---
        if existing:
            logger.info(f"Duplicate content detected. Linking to existing file ID {existing.id}")
            
            # Создаем только логическую запись о документе
            document_orm = DocumentORM(
                id=id_doc,
                user_document_id=meta.user_document_id,
                name=meta.name,
                owner_id=meta.owner_id,
                access_group_id=meta.access_group_id,
                metadata_=meta.metadata.model_dump(),
                stored_file_id=existing.id
            )
            await self.metarepo.save(document_orm)
            return document_orm.to_pydantic()

        # --- Сценарий Б: Это новый, уникальный файл ---
        else:
            logger.info("New unique content. Uploading to MinIO and creating new DB entries.")
            object_path = self._build_object_path(file_name, id_doc)

            try:
                # Шаг 1: Загружаем в MinIO
                await self.minio.put_object(object_path, content, content_type="application/octet-stream")

                # Шаг 2: Готовим ORM-объекты для обеих таблиц
                stored_file_orm = StoredFileORM(
                    content_hash=content_hash,
                    object_path=object_path,
                    size_bytes=len(content),
                    extension=Path(file_name).suffix.lower().lstrip('.')
                )
                document_orm = DocumentORM(
                    id=id_doc,
                    user_document_id=meta.user_document_id,
                    name=meta.name,
                    owner_id=meta.owner_id,
                    access_group_id=meta.access_group_id,
                    metadata_=meta.metadata.model_dump(),
                    stored_file=stored_file_orm
                )

                # Шаг 3: Сохраняем оба объекта в одной транзакции
                await self.metarepo.save_new_physical_file(stored_file_orm, document_orm)
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
    
######################## LINE
    async def save_document_lines(self, doc_id: UUID, lines: list[Line]):
        """Сохраняет разобранные строки документа в PostgreSQL."""
        logger.info(f"Saving {len(lines)} lines for document {doc_id}")
        await self.linerepo.save_lines(doc_id, lines)    
    
    async def update_lines(self, doc_id: UUID, block_id: str, new_content: str):
        """Обновляет markdown-строку, добавляя описание изображения."""
        logger.info(f"Updating alt text for block {block_id} in document {doc_id}")
        await self.linerepo.update_lines(doc_id, block_id, new_content)
        
    async def copy_lines(self, source_doc_id: UUID, target_doc_id: UUID):
        """Обновляет markdown-строку, добавляя описание изображения."""
        logger.info(f"COPY alt text for block {source_doc_id} in {target_doc_id}")
        await self.linerepo.copy_lines(source_doc_id, target_doc_id)
        
        
######################## IMG

    async def create_image_processing_task(
        self,
        doc_id: UUID,
        object_key: str,
        filename: str,
        image_hash: str,
        source_line_id: Optional[UUID] = None
    ) -> UUID:
        """
        Создает запись о задаче на обработку изображения в БД.
        """
        return await self.imagerepo.create_task(
            doc_id=doc_id,
            object_key=object_key,
            filename=filename,
            image_hash=image_hash,
            source_line_id=source_line_id
        )
        
    async def claim_image_task(self, image_id: UUID) -> Optional[DocumentImageORM]:
        """
        Атомарно захватывает задачу по обработке изображения.
        Возвращает ORM-объект задачи или None, если она уже взята в работу.
        """
        logger.info(f"Attempting to claim image processing task: {image_id}")
        return await self.imagerepo.claim_task(image_id)
    
    async def mark_image_task_done(self, image_id: UUID, result_text: str, llm_model: str):
        """Помечает задачу как успешно выполненную."""
        logger.info(f"Marking image task as done: {image_id}")
        await self.imagerepo.update_task_status(
            image_id,
            status='done',
            result_text=result_text,
            llm_model=llm_model
        )

    async def mark_image_task_failed(self, image_id: UUID, error_message: str):
        """Помечает задачу как проваленную (финальный статус)."""
        logger.error(f"Marking image task as failed: {image_id}. Reason: {error_message}")
        await self.imagerepo.update_task_status(
            image_id,
            status='failed',
            last_error=error_message
        )

    async def mark_image_task_for_retry(self, image_id: UUID, error_message: str):
        """
        Возвращает задачу в очередь для повторной попытки.
        Используется перед тем, как Celery вызовет retry.
        """
        logger.warning(f"Marking image task for retry: {image_id}. Reason: {error_message}")
        await self.imagerepo.update_task_status(
            image_id,
            status='enqueued',
            last_error=error_message
        )
        
        
    # ――― helpers ――― #
    @staticmethod
    def _build_object_path(fname: str, doc_id: UUID) -> str:
        base, ext = os.path.splitext(fname)
        ext = ext.lstrip(".") or "bin"
        return f"{ext}/{doc_id.hex}/raw/{fname}"

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
    
    
    
######################## CLI
    async def get_user_by_username(self, username: str) -> Optional[UserORM]:
        # Делегирует вызов в UserRepository
        return await self.user_repo.get_by_username(username)

    async def get_user_by_id(self, user_id: UUID) -> Optional[UserORM]:
        # Делегирует вызов в UserRepository
        return await self.user_repo.get_by_id(user_id)