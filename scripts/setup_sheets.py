import gspread
import sys
import os
from gspread.exceptions import WorksheetNotFound, SpreadsheetNotFound

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app.config.settings import settings
from app.utils.logger import log

# --- ИМПОРТИРУЕМ ВСЕ НАШИ МОДЕЛИ ---
from app.models.user import User
from app.models.pond import Pond
from app.models.product import Product
from app.models.feeding import FeedType, FeedingRow
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.models.water import WaterQualityRow
from app.models.weighing import WeighingRow
from app.models.fish import FishMoveRow
from app.models.stock import StockMoveRow


# --- ДИНАМИЧЕСКИ ОПРЕДЕЛЯЕМ СТРУКТУРУ ТАБЛИЦ ИЗ МОДЕЛЕЙ ---
# Ключ: имя листа из settings.SHEETS
# Значение: класс Pydantic модели, соответствующий этому листу
SHEET_TO_MODEL_MAP = {
    settings.SHEETS.USERS: User,
    settings.SHEETS.PONDS: Pond,
    settings.SHEETS.PRODUCTS: Product,
    settings.SHEETS.FEED_TYPES: FeedType,
    
    settings.SHEETS.SALES_ORDERS: SalesOrderRow,
    settings.SHEETS.SALES_ORDER_ITEMS: SalesOrderItemRow,
    
    settings.SHEETS.WATER_QUALITY_LOG: WaterQualityRow,
    settings.SHEETS.FEEDING_LOG: FeedingRow,
    settings.SHEETS.WEIGHING_LOG: WeighingRow,
    settings.SHEETS.FISH_MOVES_LOG: FishMoveRow,
    settings.SHEETS.STOCK_MOVES_LOG: StockMoveRow,
}

def initialize_google_sheets():
    """
    Проверяет и при необходимости создает все нужные листы и заголовки в Google Таблице,
    используя Pydantic модели как единственный источник правды.
    """
    log.info("--- Начало инициализации Google Sheets ---")
    
    # <<<--- НАЧАЛО ВОССТАНОВЛЕННОГО БЛОКА
    try:
        # 1. Подключаемся к Google API
        log.info(f"Подключение к Google Sheets с использованием файла: {settings.GOOGLE_CREDENTIALS_FILE}")
        gc = gspread.service_account(filename=settings.GOOGLE_CREDENTIALS_FILE)
        
        # 2. Открываем нашу таблицу по ID
        log.info(f"Открытие таблицы по ID: {settings.GOOGLE_SHEETS_ID}")
        spreadsheet = gc.open_by_key(settings.GOOGLE_SHEETS_ID)
        log.info(f"Успешно открыта таблица: '{spreadsheet.title}'")

    except FileNotFoundError:
        log.critical(f"Критическая ошибка: Файл с ключами '{settings.GOOGLE_CREDENTIALS_FILE}' не найден.")
        log.critical("Убедитесь, что файл credentials.json находится в корневой папке проекта.")
        return
    except SpreadsheetNotFound:
        log.critical(f"Критическая ошибка: Таблица с ID '{settings.GOOGLE_SHEETS_ID}' не найдена.")
        log.critical("Проверьте правильность GOOGLE_SHEETS_ID в вашем .env файле.")
        log.critical("Также убедитесь, что вы поделились таблицей с сервисным аккаунтом (client_email из credentials.json).")
        return
    except Exception as e:
        log.critical(f"Произошла непредвиденная ошибка при подключении к Google Sheets: {e}")
        return
    # <<<--- КОНЕЦ ВОССТАНОВЛЕННОГО БЛОКА

    # 3. Проходим по всем необходимым листам
    for sheet_name, model_class in SHEET_TO_MODEL_MAP.items():
        try:
            # Получаем заголовки прямо из класса модели
            headers = model_class.get_sheet_headers()

            # Пытаемся получить лист. Если его нет, gspread выдаст ошибку.
            # Теперь переменная 'spreadsheet' определена и эта строка будет работать
            worksheet = spreadsheet.worksheet(sheet_name)
            log.info(f"✔️ Лист '{sheet_name}' уже существует.")

            # Проверяем, есть ли заголовки (если лист пустой)
            if not worksheet.get_all_values():
                log.warning(f"Лист '{sheet_name}' пустой. Добавляю заголовки...")
                worksheet.append_row(headers, value_input_option='USER_ENTERED')
                log.info(f"    -> Заголовки для '{sheet_name}' успешно добавлены.")

        except WorksheetNotFound:
            # Если листа нет - создаем его
            log.warning(f"⚠️ Лист '{sheet_name}' не найден. Создаю новый...")
            try:
                # Получаем заголовки для создания листа
                headers = model_class.get_sheet_headers()
                # И эта строка тоже будет работать
                worksheet = spreadsheet.add_worksheet(title=sheet_name, rows="1", cols=len(headers))
                # Добавляем заголовки в первую строку
                worksheet.append_row(headers, value_input_option='USER_ENTERED')
                log.info(f"    -> Лист '{sheet_name}' успешно создан с заголовками.")
            except Exception as e:
                log.error(f"    -> ❌ Не удалось создать лист '{sheet_name}': {e}")
                
    log.info("--- Инициализация Google Sheets завершена ---")


if __name__ == "__main__":
    initialize_google_sheets()