from pydantic import BaseModel
from uuid import UUID

class Line(BaseModel):
    """Модель для одной строки документа при обработке."""
    block_id: str
    line_num: int
    content: str
    type: str

class LineInDB(Line):
    """Модель, представляющая строку, как она хранится в базе данных."""
    document_id: UUID