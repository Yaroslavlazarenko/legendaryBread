from enum import Enum
from pydantic import Field, field_validator
from app.models.base import BaseSheetModel

class UserRole(str, Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    CLIENT = "client"
    PENDING = "pending"
    BLOCKED = "blocked"

class User(BaseSheetModel):
    id: int = Field(..., alias="user_id")
    name: str = Field(..., alias="user_name")
    phone: str | None = Field(None, alias="phone_number")
    role: UserRole = Field(default=UserRole.PENDING)
    notifications_enabled: bool = Field(True, alias='notifications_enabled')

    @field_validator("phone", mode='before')
    @classmethod
    def validate_phone(cls, v):
        """Converts incoming phone number to string if it's a number."""
        if v is None:
            return None
        # This will handle both int and float inputs from the sheet
        if isinstance(v, (int, float)):
            return str(int(v)) # Convert to int first to remove potential .0 from float
        return str(v)