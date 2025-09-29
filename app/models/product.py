    
from pydantic import BaseModel, Field
from app.models.base import BaseSheetModel

class Product(BaseSheetModel):
    id: str = Field(..., alias="product_id") # <<< ИЗМЕНЕНО
    name: str
    description: str
    price: float
    unit: str
    is_available: bool

    def get_display_price(self) -> str:
        # --- ИСПРАВЛЕНИЕ: Добавляем форматирование до 2 знаков после запятой ---
        return f"{self.price:.2f} грн / {self.unit}"