from pydantic import BaseModel
from uuid import UUID
from typing import List, Dict

# class Line(BaseModel):
#     """Модель для одной строки документа при обработке."""
#     block_id: str
#     line_num: int
#     content: str
#     type: str
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
        
class LineInDB(Line):
    """Модель, представляющая строку, как она хранится в базе данных."""
    document_id: UUID