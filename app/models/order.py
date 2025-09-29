from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.models.base import BaseSheetModel

class SalesOrderRow(BaseSheetModel):
    id: str = Field(..., alias="order_id") # <<< ИЗМЕНЕНО
    ts: datetime
    client_id: int
    client_name: str
    phone: str
    status: str = "new"
    total_amount: float

    @field_validator("phone", mode='before')
    @classmethod
    def validate_phone(cls, v):
        """Converts incoming phone number to string if it's a number."""
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return str(int(v))
        return str(v)

class SalesOrderItemRow(BaseSheetModel):
    order_id: str
    product_id: str
    product_name: str
    quantity: float
    price_per_unit: float