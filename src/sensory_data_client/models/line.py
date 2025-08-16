from pydantic import BaseModel
from uuid import UUID
from typing import List, Dict


class ESLine(BaseModel):
    line_id: str
    doc_id: str
    text_content: str | None = None
    block_type: str | None = None
    position: int | None = None
    page_idx: int | None = None
    sheet_name: str | None = None
    hierarchy: str | None = None
    vector: List[float] | None = None
    source_line_id: str | None = None
    
class Line(BaseModel):
    # --- Основные поля для БД ---
    line_no: int              # Порядковый номер строки в документе
    content: str              # Текстовое содержимое строки (очищенное)
    
    # --- Метаданные от парсера ---
    block_type: str           # Тип блока из Marker: "Text", "SectionHeader", "ListItem", "Table", "Figure" и т.д.
    block_id: str             # Уникальный ID блока внутри документа (например, '/page/0/Text/5')
    page_idx: int | None = None # Номер страницы, на которой находится блок
    
    # --- Геометрические данные (ключ к подсветке и "визуальному" поиску) ---
    polygon: List[List[float]] | None = None  # Координаты 4-х углов блока [[x1,y1], [x2,y2], ...]
    bbox: List[float] | None = None          # Ограничивающий прямоугольник [x_min, y_min, x_max, y_max]
    
    # --- Контекстуальные данные (ключ к "умному" чанкингу и RAG) ---
    hierarchy: Dict[int, str] | None = None # Иерархия заголовков, в которые вложен блок. {1: "/page/0/SectionHeader/0"}
    
    # --- Для специфичных форматов ---
    sheet_name: str | None = None # Для .xlsx файлов
    class Config:
        from_attributes = True 
        populate_by_name = True # Разрешает использовать и 'line_no', и 'position'
        