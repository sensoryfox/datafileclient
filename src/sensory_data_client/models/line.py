from pydantic import BaseModel

class Line(BaseModel):
    # Поля, которые напрямую пишутся в DocumentLineORM
    line_no: int
    page_idx: int | None = None
    sheet_name: str | None = None
    block_type: str
    content: str
    block_id: str | None = None