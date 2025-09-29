# app/models/stock.py

from datetime import datetime
from enum import Enum
from pydantic import BaseModel, field_validator
from app.models.base import BaseSheetModel

class StockMoveType(str, Enum):
    INCOME = "income"     # Приход
    OUTCOME = "outcome"   # Расход

class StockMoveRow(BaseSheetModel):
    ts: datetime
    feed_type_id: str
    feed_type_name: str
    move_type: StockMoveType
    mass_kg: float
    reason: str
    user: str

    @field_validator('mass_kg')
    def validate_mass(cls, v):
        if v <= 0:
            raise ValueError("Масса должна быть положительным числом")
        return v