from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.base import BaseSheetModel
from app.config.settings import settings

class WeighingRow(BaseSheetModel):
    ts: datetime
    pond_id: str
    avg_weight_g: float
    user: str

    @field_validator('avg_weight_g')
    def validate_weight(cls, v):
        if not 0 < v <= settings.WEIGHING_AVG_WEIGHT_MAX_G:
            raise ValueError(f"Средний вес должен быть в разумных пределах (0-{settings.WEIGHING_AVG_WEIGHT_MAX_G} г)")
        return v