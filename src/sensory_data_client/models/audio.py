from pydantic import BaseModel, Field
from typing import Dict, Optional

class AudioSentenceIn(BaseModel):
    position: int = Field(..., ge=0)         # индекс предложения внутри аудио
    text: str
    start_ts: float
    end_ts: float
    speaker_label: Optional[str] = None
    speaker_idx: Optional[int] = None
    confidence: Optional[float] = None
    emo_primary: Optional[str] = None
    emo_scores: Optional[Dict[str, float]] = None
    tasks: Optional[Dict] = None             # {"tasks":[...]}