from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator
from app.models.base import BaseSheetModel

class FishMoveType(str, Enum):
    STOCKING = "stocking"         # Зарыбление (приход)
    SALE = "sale"                 # Продажа (расход)
    DEATH = "death"               # Гибель (расход)
    TRANSFER_IN = "transfer_in"   # Перевод (приход)  <-- ИЗМЕНЕНО
    TRANSFER_OUT = "transfer_out" # Перевод (расход) <-- ИЗМЕНЕНО

class FishMoveRow(BaseSheetModel):
    ts: datetime
    pond_id: str
    move_type: FishMoveType
    quantity: int
    avg_weight_g: float | None = None
    reason: str = ""
    ref: str | None = None
    user: str

    @field_validator('quantity')
    def validate_quantity(cls, v):
        if v <= 0:
            raise ValueError("Количество должно быть положительным числом")
        return v