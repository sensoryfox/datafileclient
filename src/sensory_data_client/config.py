# Файл: src/sensory_data_client/config.py

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

# --- 1. Создаем подкласс для настроек PostgreSQL ---
class PostgresConfig(BaseModel):
    # pydantic-settings автоматически приведет переменные окружения к нижнему регистру
    # PG_USER -> user, PG_PASSWORD -> password, и т.д.

    user: str
    password: str
    host: str
    port: int
    db: str

    def get_pg_dsn(self) -> str:
        """Собирает DSN для SQLAlchemy из полей этого объекта."""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


# --- 2. Создаем подкласс для настроек MinIO ---
class MinioConfig(BaseModel):

    endpoint: str
    accesskey: str
    secretkey: str
    bucket: str
    secure: bool = False


# --- 3. Основной класс для явной передачи конфигурации ---
# Теперь он состоит из двух вложенных объектов. Это и есть та "одна переменная", которую вы хотели.
class DataClientConfig(BaseModel):
    postgres: PostgresConfig
    minio: MinioConfig

# --- 4. Обновляем класс Settings для чтения из .env ---
# Он тоже будет использовать вложенную структуру. Pydantic это умеет!
class Settings(BaseSettings):
    # Вся конфигурация загрузки здесь
    model_config = SettingsConfigDict(
        env_file=".env",              # Файл, из которого читаем
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter='_'
    )

    log_level: str = Field("INFO", alias="LOG_LEVEL") # Можно использовать alias для ясности

    postgres: PostgresConfig
    minio: MinioConfig

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