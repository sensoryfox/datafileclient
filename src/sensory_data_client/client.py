import logging
import hashlib
import os
from uuid import UUID, uuid4
from typing import Optional, List
from pathlib import Path
from datetime import datetime, timezone, timedelta
from sensory_data_client.repositories import (MetaDataRepository, 
                                            ImageRepository, 
                                            LineRepository,
                                            MinioRepository,
                                            ObjectRepository,
                                            UserRepository, 
                                            GroupRepository,
                                            BillingRepository, 
                                            PermissionRepository,   
                                            TagRepository,
                                            ElasticsearchRepository,
                                            AudioRepository   
                                            )

from sensory_data_client.db import DocType, DocumentLineORM, TagORM, DocumentORM, StoredFileORM, DocumentImageORM, UserORM, SubscriptionORM
from sensory_data_client.models import AudioSentenceIn, ESLine, Line, DocumentCreate, DocumentInDB, GroupCreate, GroupInDB, GroupWithMembers
from sensory_data_client.exceptions import DocumentNotFoundError, DatabaseError, ESError, MinioError, NotFoundError 

AUDIO_EXTS = ["wav","mp3","ogg","m4a","flac","aac","wma","alac","opus"]
VIDEO_EXTS = ["mp4","mov","mkv","webm","avi"]
def get_filetype(ext):
    if ext in AUDIO_EXTS:
        return DocType.audio
    elif ext in VIDEO_EXTS:
        return DocType.video
    else:
        return DocType.generic
            
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
        image_repo: ImageRepository | None = None, 
        user_repo: UserRepository | None = None,
        group_repo: GroupRepository | None = None,
        billing_repo: BillingRepository | None = None,
        permission_repo: PermissionRepository | None = None,
        tag_repo: TagRepository | None = None,
        elastic_repo: ElasticsearchRepository | None = None,
        audio_repo: AudioRepository | None = None,
        
    ):        
        self.metarepo = meta_repo
        self.linerepo = line_repo
        self.minio = minio_repo
        self.obj = obj_repo
        self.imagerepo = image_repo
        self.user_repo = user_repo
        self.group_repo = group_repo
        self.billing_repo = billing_repo 
        self.permission_repo = permission_repo
        self.tag_repo = tag_repo
        self.es = elastic_repo
        self.audio_repo = audio_repo

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
            
        # Elastic Check
        try:
            await self.es.check_connection()
            statuses["elastic"] = "ok"
        except ESError as e:
            statuses["elastic"] = f"failed: {e}"
            
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
        ext = Path(file_name).suffix.lower().lstrip('.') or "bin"
        doc_type = get_filetype(ext)
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
                stored_file_id=existing.id,
                doc_type=doc_type
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
                    stored_file=stored_file_orm,
                    doc_type=doc_type
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
        # 1. Получаем метаданные, включая путь к файлу и его ID
        doc = await self.metarepo.get_orm(doc_id)
        if not doc:
            raise DocumentNotFoundError(f"Document with id {doc_id} not found.")

        stored_file_id = doc.stored_file_id
        object_path = doc.stored_file.object_path # Предполагая, что связь подгружена

        # 2. Удаляем запись о документе из БД. Каскад удалит строки, картинки и т.д.
        # Это нужно делать в транзакции, чтобы быть уверенным в удалении.
        await self.metarepo.delete(doc_id)
        
        # 3. Проверяем, остались ли другие документы, ссылающиеся на этот файл
        is_orphan = await self.metarepo.is_stored_file_orphan(stored_file_id)

        # 4. Если ссылок не осталось, удаляем физический файл и запись о нем
        if is_orphan:
            logger.info(f"Stored file {stored_file_id} is now an orphan. Deleting object '{object_path}' and DB record.")
            await self.minio.remove_object(object_path)
            await self.obj.delete_stored_file(stored_file_id)
        else:
            logger.info(f"Document {doc_id} deleted. Stored file {stored_file_id} is still in use by other documents.")
    
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
    
######################## DOC STATUS FOR ELASTIC

    async def is_sync_enabled(self, doc_id: UUID) -> bool:
        """Проверяет, включена ли для документа синхронизация с поисковым индексом."""
        if not self.metarepo:
            raise NotImplementedError("MetaDataRepository is not configured.")
        return await self.metarepo.get_sync_status(doc_id)

    async def set_document_sync_status(self, doc_id: UUID, is_enabled: bool) -> Optional[DocumentInDB]:
        """Включает или выключает синхронизацию документа с поисковым индексом."""
        if not self.metarepo:
            raise NotImplementedError("MetaDataRepository is not configured.")
        return await self.metarepo.set_sync_status(doc_id, is_enabled)
    
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
        
    async def get_lines_for_document(self, doc_id: UUID) -> List[DocumentLineORM]:
        """
        Получает полный список ORM-объектов строк для указанного документа.
        Идеально подходит для полной переиндексации.
        """
        if not self.linerepo:
            raise NotImplementedError("LineRepository is not configured.")
        logger.debug(f"Fetching all lines for document {doc_id}")
        return await self.linerepo.get_lines_for_document(doc_id)
        
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
    
    
######################## IMAGE
    async def get_image_description(self, source_line_id: UUID) -> Optional[str]:
        """
        Получает текстовое описание для изображения, связанного со строкой-плейсхолдером.
        Возвращает None, если описание еще не готово или не найдено.
        """
        if not self.imagerepo:
            raise NotImplementedError("ImageRepository is not configured.")
        logger.debug(f"Fetching image description for source line: {source_line_id}")
        return await self.imagerepo.get_description_by_line_id(source_line_id)

    async def get_document_images(self, doc_id: UUID) -> List[DocumentImageORM]:
        """
        Получает список всех записей об изображениях для указанного документа.
        """
        if not self.imagerepo:
            raise NotImplementedError("ImageRepository is not configured.")
        logger.debug(f"Fetching all images for document: {doc_id}")
        return await self.imagerepo.get_images_by_doc_id(doc_id)

    
######################## CLI
    
    async def create_user(self, email: str, plain_password: str) -> UserORM:
        """Делегирует создание пользователя в UserRepository."""
        if not self.user_repo:
            raise NotImplementedError("UserRepository is not configured.")
        return await self.user_repo.create_user(email, plain_password)


    async def activate_user(self, user_id: UUID) -> UserORM:
        """Активирует пользователя после верификации email."""
        if not self.user_repo:
            raise NotImplementedError("UserRepository is not configured.")
        return await self.user_repo.update_user_status(user_id, "active")

    async def get_user_by_id(self, user_id: UUID) -> Optional[UserORM]:
        """Делегирует поиск пользователя по ID в UserRepository."""
        if not self.user_repo:
            raise NotImplementedError("UserRepository is not configured.")
        return await self.user_repo.get_by_id(user_id)

    async def get_user_by_email(self, email: str) -> Optional[UserORM]:
        """Делегирует поиск пользователя по email в UserRepository."""
        if not self.user_repo:
            raise NotImplementedError("UserRepository is not configured.")
        return await self.user_repo.get_by_email(email)
    
    
######################## GROUP
    
    
    async def create_group(self, group_data: GroupCreate) -> GroupInDB:
        """Создает новую группу доступа."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        orm = await self.group_repo.create_group(group_data)
        return GroupInDB.model_validate(orm)

    async def get_group(self, group_id: UUID, with_members: bool = False) -> GroupInDB | GroupWithMembers | None:
        """Находит группу по ID. Если with_members=True, возвращает со списком участников."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        orm = await self.group_repo.get_group_by_id(group_id, with_members)
        if not orm:
            return None
        if with_members:
            return GroupWithMembers.model_validate(orm)
        return GroupInDB.model_validate(orm)

    async def list_groups(self) -> list[GroupInDB]:
        """Возвращает список всех групп доступа."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        orms = await self.group_repo.list_groups()
        return [GroupInDB.model_validate(o) for o in orms]
    
    async def add_user_to_group(self, user_id: UUID, group_id: UUID):
        """Добавляет пользователя в группу."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        await self.group_repo.add_user_to_group(user_id, group_id)

    async def remove_user_from_group(self, user_id: UUID, group_id: UUID):
        """Удаляет пользователя из группы."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        await self.group_repo.remove_user_from_group(user_id, group_id)

    async def get_user_groups(self, user_id: UUID) -> list[GroupInDB]:
        """Возвращает список групп, в которых состоит пользователь."""
        if not self.group_repo:
            raise NotImplementedError("GroupRepository is not configured.")
        orms = await self.group_repo.get_user_groups(user_id)
        return [GroupInDB.model_validate(o) for o in orms]
    
######################## PAYMENTS
    async def activate_subscription_from_payment(
        self,
        user_id: UUID,
        plan_id: UUID,
        billing_cycle: str,
        gateway_transaction_id: str,
        amount: float,
        currency: str
    ) -> SubscriptionORM:
        """
        Ключевой бизнес-метод. Собирает данные и вызывает транзакционный
        метод в репозитории для активации подписки.
        """
        if not self.billing_repo:
            raise NotImplementedError("BillingRepository is not configured.")

        now = datetime.now(timezone.utc)
        # Для более точного расчета используйте `relativedelta` из `dateutil`
        if billing_cycle == 'monthly':
            expires_at = now + timedelta(days=31)
        elif billing_cycle == 'annually':
            expires_at = now + timedelta(days=366)
        else:
            raise ValueError(f"Invalid billing cycle: {billing_cycle}")

        payment_data = {
            "amount": amount,
            "currency": currency,
            "status": "succeeded",
            "payment_gateway": "stripe", # Пример
            "gateway_transaction_id": gateway_transaction_id,
        }
        
        subscription_data = {
            "user_id": user_id,
            "plan_id": plan_id,
            "status": "active",
            "started_at": now,
            "expires_at": expires_at,
            "billing_cycle": billing_cycle,
        }

        # Делегируем всю транзакционную работу в один метод репозитория
        return await self.billing_repo.activate_subscription_transaction(
            user_id, plan_id, payment_data, subscription_data
        )
        
        
        
######################## PERMISSION
    async def grant_read_permission(self, doc_id: UUID, user_id: UUID):
        """Предоставляет пользователю право на чтение документа."""
        if not self.permission_repo:
            raise NotImplementedError("PermissionRepository is not configured.")
        await self.permission_repo.grant_permission(doc_id, user_id, "read")

    async def revoke_permission(self, doc_id: UUID, user_id: UUID):
        """Отзывает все права пользователя на документ."""
        if not self.permission_repo:
            raise NotImplementedError("PermissionRepository is not configured.")
        await self.permission_repo.revoke_permission(doc_id, user_id)

    async def get_user_shared_doc_ids(self, user_id: UUID) -> List[UUID]:
        """Возвращает список ID документов, расшаренных для пользователя."""
        if not self.permission_repo:
            raise NotImplementedError("PermissionRepository is not configured.")
        return await self.permission_repo.get_user_shared_doc_ids(user_id)

    # =================== НОВЫЕ МЕТОДЫ ДЛЯ ТЕГОВ ===================
    
######################## TEGS
    async def add_tags_to_document(self, doc_id: UUID, tags: List[str], source: str = "manual"):
        """Добавляет список тегов к документу."""
        if not self.tag_repo:
            raise NotImplementedError("TagRepository is not configured.")
        await self.tag_repo.add_tags_to_document(doc_id, tags, source)
        
    async def get_document_tags(self, doc_id: UUID) -> List[TagORM]:
        """Получает список тегов для документа."""
        if not self.tag_repo:
            raise NotImplementedError("TagRepository is not configured.")
        return await self.tag_repo.get_document_tags(doc_id)

    async def set_tag_vector(self, tag_id: UUID, vector: List[float]):
        """Устанавливает вектор для тега."""
        if not self.tag_repo:
            raise NotImplementedError("TagRepository is not configured.")
        await self.tag_repo.set_tag_vector(tag_id, vector)
        
        
######################## ELASTIC

    async def get_lines_with_vectors_from_es(
        self,
        doc_id: UUID,
        include_types: list[str] | None = None,
        exclude_types: list[str] | None = None,
        limit: int | None = None
    ) -> list[ESLine]:
        if not self.es:
            raise NotImplementedError("ElasticsearchRepository is not configured.")
        return await self.es.get_lines_with_vectors(
            doc_id=doc_id, include_types=include_types, exclude_types=exclude_types, limit=limit
        )
        
######################## AUDIO
    async def save_audio_sentences(self, doc_id: UUID, sentences: list[AudioSentenceIn]) -> int:
        if not self.audio_repo:
            raise NotImplementedError("AudioMetaRepository is not configured.")
        return await self.audio_repo.replace_audio_sentences_with_meta(doc_id, sentences)