from pydantic import BaseModel, Field

class BaseSheetModel(BaseModel):
    """
    Базовая модель для всех сущностей, которые хранятся в Google Sheets.
    Предоставляет методы для автоматической генерации заголовков и строк.
    """

    @classmethod
    def get_sheet_headers(cls) -> list[str]:
        """
        Динамически генерирует список заголовков для Google Sheets,
        используя псевдонимы (aliases) полей, если они есть.
        """
        headers = []
        # model_fields - это словарь полей модели в Pydantic v2
        for field_name, field_info in cls.model_fields.items():
            # Если у поля есть псевдоним (alias), используем его. Иначе - имя поля.
            headers.append(field_info.alias or field_name)
        return headers

    def to_sheet_row(self) -> list:
        """
        Динамически преобразует экземпляр модели в список для записи в Google Sheets.
        Порядок значений соответствует порядку в get_sheet_headers().
        """
        # model_dump преобразует модель в словарь. 
        # by_alias=True гарантирует, что ключами будут псевдонимы (user_id вместо id).
        # .values() возвращает значения в порядке объявления полей.
        
        # Обработка Enum и datetime
        row_data = self.model_dump(by_alias=True)
        processed_values = []
        for value in row_data.values():
            if hasattr(value, 'value'): # Проверяем, является ли объект Enum
                processed_values.append(value.value)
            elif hasattr(value, 'isoformat'): # Проверяем, является ли объект datetime/date
                processed_values.append(value.isoformat())
            else:
                processed_values.append(value)
        return processed_values