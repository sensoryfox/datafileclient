# Файл: src/sensory_data_client/config.py

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# --- 1. Создаем подкласс для настроек PostgreSQL ---
class PostgresConfig(BaseModel):
    user: str = "postgres"
    password: str = "postgres"
    host: str = "localhost"
    port: int = 5422
    db: str = "documents"

    def get_pg_dsn(self) -> str:
        """Собирает DSN для SQLAlchemy из полей этого объекта."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


# --- 2. Создаем подкласс для настроек MinIO ---
class MinioConfig(BaseModel):
    endpoint: str = "localhost:9000"
    accesskey: str = "minioadmin"
    secretkey: str = "minioadmin"
    bucket: str = "documents"
    secure: bool = False

# --- 3. Основной класс для явной передачи конфигурации ---
# Теперь он состоит из двух вложенных объектов. Это и есть та "одна переменная", которую вы хотели.
class DataClientConfig(BaseModel):
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    minio: MinioConfig = Field(default_factory=MinioConfig)

# --- 4. Обновляем класс Settings для чтения из .env ---
# Он тоже будет использовать вложенную структуру. Pydantic это умеет!
class Settings(BaseSettings):
    # Вся конфигурация загрузки здесь
    model_config = SettingsConfigDict(
        env_file=".env",              # Файл, из которого читаем
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter='_',
        extra='ignore'
    )

    log_level: str = Field("INFO", alias="LOG_LEVEL") # Можно использовать alias для ясности

    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    minio: MinioConfig = Field(default_factory=MinioConfig)

# --- ИСПРАВЛЕНО: Ленивая инициализация ---
_cached_settings: Optional[Settings] = None

def get_settings() -> Settings:
    """
    Возвращает синглтон-экземпляр настроек, создавая его при первом вызове.
    Это предотвращает ошибки валидации при импорте.
    """
    global _cached_settings
    if _cached_settings is None:
        _cached_settings = Settings()
    return _cached_settings