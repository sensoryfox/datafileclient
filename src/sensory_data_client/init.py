
# src/data_client/init.py
import asyncio
import logging
from alembic.config import Config
from alembic import command
from minio import Minio
from minio.error import S3Error

from .config import settings

# Настраиваем логирование, чтобы видеть, что происходит
logging.basicConfig(level="INFO", format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


async def init_minio():
    """Инициализация MinIO: создание бакета, если он не существует."""
    logger.info("Initializing MinIO...")
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    try:
        found = client.bucket_exists(settings.minio_bucket)
        if not found:
            client.make_bucket(settings.minio_bucket)
            logger.info(f"Bucket '{settings.minio_bucket}' created.")
        else:
            logger.info(f"Bucket '{settings.minio_bucket}' already exists.")
    except S3Error as e:
        logger.error(f"MinIO initialization failed: {e}")
        raise


def init_postgres():
    """Применение миграций Alembic."""
    logger.info("Initializing PostgreSQL (running migrations)...")
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("PostgreSQL migrations applied successfully.")
    except Exception as e:
        logger.error(f"PostgreSQL initialization failed: {e}")
        raise


async def main():
    logger.info("--- Starting Data-Client Initialization ---")
    await init_minio()
    # Миграции - синхронная операция, запускаем в executor'е, чтобы не блокировать event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, init_postgres)
    logger.info("--- Initialization Complete ---")


if __name__ == "__main__":
    asyncio.run(main())