import os
import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer
from testcontainers.minio import MinioContainer
from sqlalchemy.ext.asyncio import create_async_engine

# Импортируем Base для создания/удаления таблиц
from sensory_data_client.db.base import Base
# Импортируем нашу фабрику, чтобы тесты работали как реальное приложение
from sensory_data_client import DataClient, create_data_client


@pytest.fixture(scope="session", autouse=True)
def _test_containers(request):
    """
    Запускает Docker-контейнеры один раз на всю тестовую сессию.
    Устанавливает переменные окружения для подключения к ним.
    """
    print("\nStarting test containers...")
    postgres = PostgresContainer("postgres:15")
    minio = MinioContainer("minio/minio:latest", access_key="minioadmin", secret_key="minioadmin")

    postgres.start()
    minio.start()

    # Устанавливаем переменные окружения, которые прочитает get_settings()
    os.environ["POSTGRES_USER"] = postgres.username
    os.environ["POSTGRES_PASSWORD"] = postgres.password
    os.environ["POSTGRES_DB"] = postgres.dbname
    os.environ["POSTGRES_HOST"] = postgres.get_container_host_ip()
    os.environ["POSTGRES_PORT"] = str(postgres.get_exposed_port(5432))

    minio_config = minio.get_config()
    os.environ["MINIO_ENDPOINT"] = minio_config["endpoint"].replace("http://", "")
    os.environ["MINIO_ACCESS_KEY"] = minio_config["access_key"]
    os.environ["MINIO_SECRET_KEY"] = minio_config["secret_key"]
    os.environ["MINIO_SECURE"] = "False"
    os.environ["MINIO_BUCKET"] = "test-bucket"

    print("Test containers are running and environment is set.")
    yield
    print("\nStopping test containers...")
    postgres.stop()
    minio.stop()


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    """
    Создает движок для тестовой БД и ГАРАНТИРОВАННО создает в ней все таблицы.
    После теста все таблицы удаляются для полной изоляции.
    """
    from sensory_data_client.config import get_settings
    settings = get_settings()
    engine = create_async_engine(settings.postgres.get_pg_dsn())

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def data_client(db_engine) -> DataClient:
    """
    Собирает DataClient, готовый к работе.
    Использует фабрику create_data_client для максимального соответствия
    реальному приложению.
    """
    client = create_data_client()
    # Убеждаемся, что тестовый бакет существует
    await client.minio.check_connection()
    return client