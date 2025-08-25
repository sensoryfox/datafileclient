# Файл: src/sensory_data_client/__init__.py

from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import QueuePool
from .client import DataClient
# Импортируем НОВЫЕ конфигурационные классы
from .config import get_settings, DataClientConfig, PostgresConfig, MinioConfig, ElasticsearchConfig
from .repositories.pg_repositoryMeta import MetaDataRepository
from .repositories.lines_repo.pg_repositoryLine import LineRepository
from .repositories.minio_repository import MinioRepository
from .repositories.pg_repositoryObj import ObjectRepository
from .repositories.lines_repo.pg_repositoryImage import ImageRepository 
from .repositories.auth.pg_repositoryUser import UserRepository 
from .repositories.auth.pg_repositoryGroup import GroupRepository
from .repositories.auth.pg_repositoryBilling import BillingRepository
from .repositories.auth.pg_repositoryPermission import PermissionRepository
from .repositories.es_repository import ElasticsearchRepository
from .repositories.lines_repo.pg_repositoryAudio import AudioRepository
from .repositories.lines_repo.pg_repositoryDoc import DocumentDetailsRepository
from .repositories.tags.pg_repository_autotag import AutotagRepository
from .repositories.tags.pg_repositoryTag import TagRepository

    
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
    engine = create_async_engine(
            config.postgres.get_pg_dsn(),
            pool_size=config.postgres.pool_size,
            max_overflow=config.postgres.max_overflow,
            pool_timeout=config.postgres.pool_timeout,
            pool_recycle=config.postgres.pool_recycle,
            pool_pre_ping=True,
            connect_args={
                # Вот правильное место для server_settings
                "server_settings": {
                    "application_name": config.postgres.application_name
                }
            }
        )
    
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    doc_details_repo = DocumentDetailsRepository() # Он stateless, ему не нужен session_factory
    image_repo = ImageRepository(session_factory)
    audio_repo = AudioRepository(session_factory)

    line_repo = LineRepository(
        session_factory=session_factory,
        doc_repo=doc_details_repo,
        img_repo=image_repo,
        audio_repo=audio_repo
    )
    meta_repo = MetaDataRepository(session_factory)
    obj_repo = ObjectRepository(session_factory)
    user_repo = UserRepository(session_factory)
    group_repo = GroupRepository(session_factory)
    billing_repo = BillingRepository(session_factory)
    tag_repo = TagRepository(session_factory)
    autotagrepo = AutotagRepository(session_factory)
    permission_repo = PermissionRepository(session_factory)
    es_repo = ElasticsearchRepository(config.elastic)
    minio_repo = MinioRepository(config.minio)

    # 3. Собираем и возвращаем клиент
    client = DataClient(
        engine=engine,
        meta_repo=meta_repo,
        line_repo=line_repo,
        minio_repo=minio_repo,
        obj_repo=obj_repo,
        image_repo=image_repo,
        user_repo=user_repo,
        group_repo=group_repo,
        billing_repo=billing_repo,
        permission_repo=permission_repo,
        elastic_repo=es_repo,
        audio_repo=audio_repo,
        tag_repo=tag_repo,
        autotagrepo=autotagrepo,
        
    )  
    try:
        client._engine = engine
        async def _aclose():
            await engine.dispose()
        client.aclose = _aclose
    except Exception:
        pass

    return client

__all__ = [
    "DataClient", "create_data_client", 
    "DataClientConfig", "PostgresConfig", "MinioConfig", "ElasticsearchConfig", 
    "DocumentNotFoundError", "DatabaseError", "MinioError"
]