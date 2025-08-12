# src/api/v1/documents.py
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status
from typing import Annotated, Optional
from uuid import UUID
from sensory_data_client.db import UserORM
from sensory_data_client import DataClient # UserORM импортируется из клиента
from sensory_data_client.models.document import DocumentInDB # Наша новая Pydantic-модель
from .auth import get_current_active_user
from sensory_data_client import create_data_client # Фабрика для DataClient

router = APIRouter(prefix="/documents", tags=["User Documents"])

@router.post("/upload", response_model=DocumentInDB) # Указываем модель ответа
async def upload_document(
    # Зависимости FastAPI для получения пользователя и клиента данных
    current_user: Annotated[UserORM, Depends(get_current_active_user)],
    data_client: Annotated[DataClient, Depends(create_data_client)],
    # Параметры из multipart/form-data
    file: UploadFile = File(...),
    upload_type: str = Form(..., pattern="^(individual|group)$"),
    target_group_id: Optional[UUID] = Form(None),
):
    """
    Загружает документ от имени текущего пользователя.
    - `upload_type='individual'`: Файл всегда приватный и парсится заново.
    - `upload_type='group'`: Файл становится групповым. Если такой же файл уже есть в группе, его контент будет переиспользован без повторного парсинга.
    """
    # --- Авторизация ---
    if upload_type == "group":
        if not target_group_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="target_group_id is required for group upload.")
        
        user_group_ids = {group.id for group in current_user.groups}
        if target_group_id not in user_group_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not a member of the target group.")

    file_content = await file.read()

    try:
        # --- Вызов ядра логики ---
        new_doc = await data_client.upload_file(
            file_content=file_content,
            file_name=file.filename,
            owner_id=current_user.id,
            upload_type=upload_type,
            target_group_id=target_group_id
        )
        return new_doc

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # Здесь должно быть логирование ошибки
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An internal error occurred.")