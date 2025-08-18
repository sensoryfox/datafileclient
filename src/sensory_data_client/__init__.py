# Файл: src/sensory_data_client/__init__.py

from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from .client import DataClient
# Импортируем НОВЫЕ конфигурационные классы
from .config import get_settings, DataClientConfig, PostgresConfig, MinioConfig, ElasticsearchConfig
from .repositories.pg_repositoryMeta import MetaDataRepository
from .repositories.pg_repositoryLine import LineRepository
from .repositories.minio_repository import MinioRepository
from .repositories.pg_repositoryObj import ObjectRepository
from .repositories.pg_repositoryImage import ImageRepository 
from .repositories.pg_repositoryUser import UserRepository 
from .repositories.pg_repositoryGroup import GroupRepository
from .repositories.pg_repositoryBilling import BillingRepository
from .repositories.pg_repositoryPermission import PermissionRepository
from .repositories.pg_repositoryTag import TagRepository
from .repositories.es_repository import ElasticsearchRepository
from .repositories.pg_repositoryAudioMeta import AudioRepository

    
from .exceptions import *

def create_data_client(config: Optional[DataClientConfig] = None) -> DataClient:
    """
    Фабричная функция для создания и конфигурации DataClient.

    :param config: Единый объект с настройками. 
                   Если не предоставлен, используются переменные окружения.
    :return: Сконфигурированный экземпляр DataClient.
    """
    # --- Ключевое изменение! ---
    # Если конфиг не передан, создаем его из глобальных настроек .env
    # Это избавляет от громоздкого if/else для каждого параметра.
    if config is None:
        # Получаем настройки только когда они нужны
        s = get_settings()
        config = DataClientConfig(postgres=s.postgres, minio=s.minio, elastic=s.elastic)
    
    # 1. Создаем зависимости для PostgreSQL, используя вложенный объект
    engine = create_async_engine(config.postgres.get_pg_dsn())
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    line_repo = LineRepository(session_factory)
    meta_repo = MetaDataRepository(session_factory)
    obj_repo = ObjectRepository(session_factory)
    image_repo = ImageRepository(session_factory)
    user_repo = UserRepository(session_factory)
    group_repo = GroupRepository(session_factory)
    billing_repo = BillingRepository(session_factory)
    tag_repo = TagRepository(session_factory)
    permission_repo = PermissionRepository(session_factory)
    es_repo = ElasticsearchRepository(config.elastic)
    audio_repo = AudioRepository(session_factory)

    # 2. Создаем зависимость для MinIO.
    # Распаковываем словарь из Pydantic-модели прямо в конструктор. Элегантно!
    minio_repo = MinioRepository(config.minio)

    # 3. Собираем и возвращаем клиент
    client = DataClient(
        meta_repo=meta_repo,
        line_repo=line_repo,
        minio_repo=minio_repo,
        obj_repo=obj_repo,
        image_repo=image_repo,
        user_repo=user_repo,
        group_repo=group_repo,
        billing_repo=billing_repo,
        tag_repo=tag_repo,
        permission_repo=permission_repo,
        elastic_repo=es_repo,
        audio_repo=audio_repo,
        
    )
    return client

__all__ = [
    "DataClient", "create_data_client", 
    "DataClientConfig", "PostgresConfig", "MinioConfig", "ElasticsearchConfig", 
    "DocumentNotFoundError", "DatabaseError", "MinioError"
]