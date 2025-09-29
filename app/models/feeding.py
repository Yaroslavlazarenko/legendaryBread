from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.config.settings import settings
from app.models.base import BaseSheetModel

class FeedType(BaseSheetModel):
    id: str = Field(..., alias="feed_id")
    name: str
    is_active: bool = True

class FeedingRow(BaseSheetModel):
    ts: datetime
    pond_id: str
    feed_type: str
    mass_kg: float
    user: str

    @field_validator('mass_kg')
    def validate_mass(cls, v):
        if not 0 < v <= settings.MAX_FEEDING_MASS_KG:
            raise ValueError(f"Масса корма должна быть в диапазоне от 0 до {settings.MAX_FEEDING_MASS_KG} кг")
        return v