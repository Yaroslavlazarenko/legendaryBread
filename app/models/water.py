from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from app.config.settings import settings
from app.models.base import BaseSheetModel

class WaterQualityRow(BaseSheetModel):
    ts: datetime
    pond_id: str
    dissolved_O2_mgL: float
    temperature_C: float
    notes: str = ""
    user: str

    @field_validator('dissolved_O2_mgL')
    def validate_do(cls, v):
        # Используем значения из settings
        if not settings.DO_MIN <= v <= settings.DO_MAX:
            raise ValueError(f"DO должен быть в диапазоне от {settings.DO_MIN} до {settings.DO_MAX} мг/л")
        return v

    @field_validator('temperature_C')
    def validate_temp(cls, v):
        # Используем значения из settings
        if not settings.TEMP_MIN <= v <= settings.TEMP_MAX:
            raise ValueError(f"Температура должна быть в диапазоне от {settings.TEMP_MIN} до {settings.TEMP_MAX} °C")
        return v
    
    def is_critical(self) -> bool:
        """Проверяет, выходят ли параметры за критические пороги."""
        return (self.dissolved_O2_mgL < settings.DO_MIN or
                self.temperature_C < settings.TEMP_MIN or
                self.temperature_C > settings.TEMP_MAX)