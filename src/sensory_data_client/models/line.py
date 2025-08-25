from __future__ import annotations

from pydantic import BaseModel, Field, ConfigDict, model_validator
from sensory_data_client.utils.cli_utils import parse_image_hash_from_md
from uuid import UUID
from typing import List, Dict, Optional, Any


class ESLine(BaseModel):
    line_id: str
    doc_id: str
    text_content: str | None = None
    block_type: str | None = None
    position: int | None = None
    page_idx: int | None = None
    hierarchy: str | None = None
    vector: List[float] | None = None
    source_line_id: str | None = None
    
    
class RawLine(BaseModel):
    """Базовая модель, соответствующая таблице raw_lines."""
    id: UUID
    doc_id: UUID
    position: int
    type: str = Field(alias="block_type")
    content: str
    
    class Config:
        from_attributes = True 
        populate_by_name = True 
    
class DocumentLineDetails(BaseModel):
    """Детали для текстовых/структурных блоков."""
    page_idx: Optional[int] = None
    block_id: Optional[str] = None
    polygon: List[List[float]] | None = None  # Координаты 4-х углов блока [[x1,y1], [x2,y2], ...]
    bbox: List[float] | None = None          # Ограничивающий прямоугольник [x_min, y_min, x_max, y_max]
    hierarchy: Optional[Dict[int, str]] = None
    class Config:
        from_attributes = True 
        populate_by_name = True # Разрешает использовать и 'line_no', и 'position'
     
class ImageLineDetails(BaseModel):
    """Детали для изображений."""
    result_text: Optional[str] = None
    ocr_text: Optional[str] = None
    
    class Config:
        from_attributes = True 
        populate_by_name = True
        
class AudioLineDetails(BaseModel):
    start_ts: Optional[float] = None
    end_ts: Optional[float] = None
    duration: Optional[float] = None
    speaker_label: Optional[str] = None
    speaker_idx: Optional[int] = None
    confidence: Optional[float] = None
    emo_primary: Optional[str] = None
    emo_scores: Optional[dict] = None

    tasks: Optional[dict] = None # например {"tasks":["transcribe","diarization","emotion"]}

    model_config = {"from_attributes": True}

# Единая модель для входных и выходных данных
class EnrichedLine(RawLine, DocumentLineDetails, ImageLineDetails, AudioLineDetails):   
    pass

class NormLine(BaseModel):
    """
    Нормализованная и провалидированная строка, пригодная для записи.
    Используем Pydantic v2: model_validator для нормализации и авто‑правил.

    Важное:
    - Только field 'position' определяет место строки (line_no игнорируется).
    - block_type приводим к lowercase.
    - Если block_type указывает на изображение и нет image_hash — пытаемся достать из контента.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
        extra="allow",
    )

    # ядро
    position: int
    block_type: str = Field(alias="type", default="text")
    content: str = ""

    # детали документа
    page_idx: int | None = None
    block_id: str | None = None
    geometry: dict | None = None
    polygon: list[list[float]] | None = None
    bbox: list[float] | None = None
    hierarchy: dict | list | None = None
    attrs: dict | list | None = None
    # изображение
    is_image: bool | None = None
    image_hash: str | None = None
    object_key: str | None = None
    filename: str | None = None
    status: str | None = None
    result_text: str | None = None
    ocr_text: str | None = None

    # аудио
    start_ts: float | None = None
    end_ts: float | None = None
    duration: float | None = None
    speaker_label: str | None = None
    speaker_idx: int | None = None
    confidence: float | None = None
    emo_primary: str | None = None
    emo_scores: dict | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_input(cls, data: Any):
        """
        Нормализуем вход:
        - переносим alias 'type' в 'block_type' если нужно;
        - приводим content к строке;
        """
        if isinstance(data, dict):
            # alias 'type' -> 'block_type' (Pydantic сам обрабатывает alias, но пусть будет явнее)
            if "block_type" not in data and "type" in data:
                data["block_type"] = data.get("type")
            # content must be string
            if "content" in data and data["content"] is None:
                data["content"] = ""
        return data

    @model_validator(mode="after")
    def _normalize(self):
        # block_type to lowercase
        if self.block_type:
            self.block_type = str(self.block_type).lower()

        # content по умолчанию — пустая строка
        self.content = self.content or ""

        # если это изображение и нет image_hash — достанем из контента
        if self._is_image_block() and not self.image_hash:
            parsed = parse_image_hash_from_md(self.content)
            if parsed:
                self.image_hash = parsed
                # filename можно подставить, если не передали
                if not self.filename:
                    self.filename = f"{parsed}.png"

        return self

    def _is_image_block(self) -> bool:
        if self.is_image:
            return True
        bt = (self.block_type or "").lower()
        return bt in {"image", "image_placeholder"}#, "img", "picture", "figure", "photo", "diagram"}



Line = EnrichedLine # Используем EnrichedLine как основной тип