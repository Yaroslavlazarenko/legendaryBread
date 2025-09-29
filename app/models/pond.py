from pydantic import BaseModel, Field, field_validator
from datetime import date
from app.models.base import BaseSheetModel

class Pond(BaseSheetModel):
    id: str = Field(..., alias="pond_id") # <<< ИЗМЕНЕНО
    name: str
    type: str = "pond"
    species: str | None = None
    stocking_date: date | None = None
    initial_qty: int | None = None
    notes: str = ""
    is_active: bool

    @field_validator('initial_qty')
    def validate_initial_qty(cls, v):
        if v is not None and v < 0:
            raise ValueError("Начальное количество рыбы не может быть отрицательным.")
        return v

    def __str__(self):
        # Теперь этот метод работает правильно, так как поле `id` существует
        return f"{self.name} ({self.id})"