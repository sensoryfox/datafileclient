# Файл: sensory_data_client/models/group.py

from __future__ import annotations
from uuid import UUID
from typing import List
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# Для информации о пользователе в контексте группы
class UserInfo(BaseModel):
    id: UUID
    email: str

    model_config = {"from_attributes": True}

# Схема для создания новой группы
class GroupCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    description: str | None = None

# Схема для группы, возвращаемая из БД
class GroupInDB(GroupCreate):
    id: UUID
    created_at: datetime
    edited_at: datetime

    model_config = {"from_attributes": True}

# Расширенная схема группы со списком ее участников
class GroupWithMembers(GroupInDB):
    users: List[UserInfo] = []