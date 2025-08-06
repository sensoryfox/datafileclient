# Файл: src/sensory_data_client/__init__.py

from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from .client import DataClient
# Импортируем НОВЫЕ конфигурационные классы
from .config import get_settings, DataClientConfig, PostgresConfig, MinioConfig
from .repositories.pg_repositoryMeta import MetaDataRepository
from .repositories.pg_repositoryLine import LineRepository
from .repositories.minio_repository import MinioRepository
from .repositories.pg_repositoryObj import ObjectRepository
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
        config = DataClientConfig(postgres=s.postgres, minio=s.minio)
    
    # 1. Создаем зависимости для PostgreSQL, используя вложенный объект
    engine = create_async_engine(config.postgres.get_pg_dsn())
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    
    meta_repo = MetaDataRepository(session_factory)
    line_repo = LineRepository(session_factory)
    obj_repo = LineRepository(ObjectRepository)

    # 2. Создаем зависимость для MinIO.
    # Распаковываем словарь из Pydantic-модели прямо в конструктор. Элегантно!
    minio_repo = MinioRepository(config.minio)

    # 3. Собираем и возвращаем клиент
    client = DataClient(
        meta_repo=meta_repo,
        line_repo=line_repo,
        minio_repo=minio_repo,
        obj_repo=obj_repo
    )
    return client

__all__ = [
    "DataClient", "create_data_client", 
    "DataClientConfig", "PostgresConfig", "MinioConfig", 
    "DocumentNotFoundError", "DatabaseError", "MinioError"
]