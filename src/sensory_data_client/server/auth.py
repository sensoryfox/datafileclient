import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from uuid import UUID

from sensory_data_client import DataClient, UserORM # Предполагается, что UserORM будет в клиенте
from src.core.config import settings
from sensory_data_client import (
    create_data_client,
    DataClientConfig,
    PostgresConfig,
    MinioConfig
)
# --- 1. Конфигурация ---
# Схема для аутентификации с паролем и OAuth2.
# tokenUrl указывает на эндпоинт, который будет выдавать токен.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# Контекст для хеширования паролей. Используем bcrypt - надежный стандарт.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Ключ и алгоритм для подписи JWT-токенов. Берутся из настроек.
SECRET_KEY = settings.auth.secret_key
ALGORITHM = settings.auth.algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = settings.auth.access_token_expire_minutes


# --- 2. Pydantic-схемы ---
# Модель для данных, которые мы храним внутри JWT токена
class TokenData(BaseModel):
    sub: str | None = None # 'sub' (subject) - стандартное поле для идентификатора пользователя

# Модель для ответа с токеном
class Token(BaseModel):
    access_token: str
    token_type: str

# --- 3. Функции-хелперы ---
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, соответствует ли обычный пароль хешированному."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Создает хеш из обычного пароля."""
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    """Создает новый JWT-токен."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# --- 4. Главная зависимость FastAPI ---
async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    data_client: Annotated[DataClient, Depends(create_data_client)],
) -> UserORM:
    """
    Зависимость для проверки токена и получения текущего пользователя.
    Это "сторож" для защищенных эндпоинтов.

    1. Получает токен из заголовка Authorization.
    2. Декодирует и проверяет подпись/срок действия.
    3. Извлекает ID пользователя (sub).
    4. Запрашивает пользователя в БД через DataClient.
    5. Возвращает ORM-объект пользователя или выбрасывает ошибку 401.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        token_data = TokenData(sub=user_id_str)
    except JWTError:
        raise credentials_exception

    # Используем DataClient для получения пользователя из БД
    user = await data_client.get_user_by_id(UUID(token_data.sub))
    
    if user is None:
        raise credentials_exception
        
    # Здесь можно добавить проверку, например, user.is_active
    # if not user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")

    return user

async def get_current_active_user(
    current_user: Annotated[UserORM, Depends(get_current_user)]
) -> UserORM:
    """Зависимость, которая проверяет, что пользователь не только аутентифицирован, но и активен."""
    # if not current_user.is_active: # <-- Раскомментировать, когда добавите поле is_active
    #     raise HTTPException(status_code=400, detail="Inactive user")
    return current_user