import gspread
from functools import lru_cache
from app.config.settings import settings
from app.utils.logger import log

class GoogleSheetsClient:
    def __init__(self):
        try:
            gc = gspread.service_account(filename=settings.GOOGLE_CREDENTIALS_FILE)
            self.spreadsheet = gc.open_by_key(settings.GOOGLE_SHEETS_ID)
            log.info("Успешное подключение к Google Sheets.")
        except Exception as e:
            log.critical(f"Ошибка подключения к Google Sheets: {e}")
            raise

    # @lru_cache - Кэш нужно сбрасывать при изменениях, поэтому для справочников его лучше убрать или сделать умнее
    def get_sheet_data(self, sheet_name: str) -> list[dict]:
        """Получает все данные с листа."""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            # Очищаем кэш для этого метода, если он используется
            # GoogleSheetsClient.get_sheet_data.cache_clear()
            return worksheet.get_all_records()
        except gspread.exceptions.WorksheetNotFound:
            log.error(f"Лист '{sheet_name}' не найден.")
            return []
        except Exception as e:
            log.error(f"Ошибка при чтении листа '{sheet_name}': {e}")
            return []

    def append_row(self, sheet_name: str, data: list):
        """Добавляет строку в конец указанного листа (журнала)."""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            worksheet.append_row(data, value_input_option='USER_ENTERED')
            log.info(f"Строка добавлена в лист '{sheet_name}'.")
        except Exception as e:
            log.error(f"Ошибка при записи в лист '{sheet_name}': {e}")
    
    def update_cell_by_match(self, sheet_name: str, match_col: int, match_val: str | int, target_col: int, new_val: str):
        """Находит строку по значению в колонке и обновляет ячейку в другой колонке."""
        try:
            worksheet = self.spreadsheet.worksheet(sheet_name)
            cell = worksheet.find(str(match_val), in_column=match_col)
            if not cell:
                log.warning(f"Не найдена запись '{match_val}' в листе '{sheet_name}' для обновления.")
                return False
            worksheet.update_cell(cell.row, target_col, new_val)
            log.info(f"В листе '{sheet_name}' обновлена ячейка ({cell.row}, {target_col}) на '{new_val}'.")
            return True
        except Exception as e:
            log.error(f"Ошибка при обновлении ячейки в '{sheet_name}': {e}")
            return False

gs_client = GoogleSheetsClient()