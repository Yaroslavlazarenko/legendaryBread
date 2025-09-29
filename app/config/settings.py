import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Определяем базовую директорию проекта
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class SheetNames:
    # Справочники
    USERS = "USERS"
    PONDS = "PONDS"
    FEED_TYPES = "FEED_TYPES"
    PRODUCTS = "PRODUCTS"
    # Журналы
    WATER_QUALITY_LOG = "WATER_QUALITY_LOG"
    FEEDING_LOG = "FEEDING_LOG"
    WEIGHING_LOG = "WEIGHING_LOG"
    FISH_MOVES_LOG = "FISH_MOVES_LOG"
    STOCK_MOVES_LOG = "STOCK_MOVES_LOG"
    SALES_ORDERS = "SALES_ORDERS"
    SALES_ORDER_ITEMS = "SALES_ORDER_ITEMS"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, '.env'),
        env_file_encoding='utf-8',
        extra='ignore'
    )

    # --- Основные настройки, выносимые в .env ---
    BOT_TOKEN: str
    GOOGLE_SHEETS_ID: str
    WEBHOOK_URL: str | None = None
    LOG_LEVEL: str = "INFO"
    TIMEZONE: str = "Europe/Kiev"
    
    # --- Путь к файлу-ключу (обычно не меняется) ---
    GOOGLE_CREDENTIALS_FILE: str = os.path.join(BASE_DIR, 'credentials.json')

    # --- Бизнес-логика и правила валидации (можно переопределить в .env при необходимости) ---
    # Критические пороги для алертов
    DO_MIN: float = 4.0
    DO_MAX: float = 20.0
    TEMP_MIN: float = -2.0
    TEMP_MAX: float = 35.0

    # Пороги для взвешивания
    WEIGHING_AVG_WEIGHT_MAX_G: int = 10000

    # Пороги для валидации вводимых данных
    MAX_FEEDING_MASS_KG: int = 500
    MAX_AVG_FISH_WEIGHT_G: int = 10000
    
    # Настройки интерфейса
    PAGINATION_PAGE_SIZE: int = 5

    # Добавляем константы для удобного доступа
    SHEETS: SheetNames = SheetNames()

settings = Settings()