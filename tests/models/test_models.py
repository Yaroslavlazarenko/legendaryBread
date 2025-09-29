import pytest
from datetime import datetime, date
from pydantic import ValidationError

# Импортируем все модели для тестирования
from app.models.water import WaterQualityRow
from app.models.feeding import FeedingRow
from app.models.weighing import WeighingRow
from app.models.pond import Pond
from app.models.fish import FishMoveRow, FishMoveType
from app.models.stock import StockMoveRow, StockMoveType
from app.models.user import User, UserRole
from app.models.product import Product
from app.config.settings import settings


# --- Тесты для WaterQualityRow ---

def test_water_quality_row_happy_path():
    """Тест: Успешное создание WaterQualityRow с валидными данными."""
    data = {
        'ts': datetime.now(), 'pond_id': 'P-001', 'user': 'test_user',
        'dissolved_O2_mgL': 8.5, 'temperature_C': 15.0
    }
    try:
        WaterQualityRow.model_validate(data)
    except ValidationError:
        pytest.fail("Валидные данные не должны вызывать ошибку валидации.")

@pytest.mark.parametrize("field, value, error_msg", [
    ("dissolved_O2_mgL", -1, "DO должен быть в диапазоне"),
    ("dissolved_O2_mgL", 21, "DO должен быть в диапазоне"),
    ("temperature_C", -3, "Температура должна быть в диапазоне"),
    ("temperature_C", 36, "Температура должна быть в диапазоне"),
])
def test_water_quality_row_invalid_ranges(field, value, error_msg):
    """Тест: Невалидные значения DO и температуры вызывают ValidationError."""
    invalid_data = {
        'ts': datetime.now(), 'pond_id': 'P-001', 'user': 'test_user',
        'dissolved_O2_mgL': 8.5, 'temperature_C': 15.0
    }
    invalid_data[field] = value
    with pytest.raises(ValidationError, match=error_msg):
        WaterQualityRow.model_validate(invalid_data)

def test_water_quality_is_critical():
    """Тест: Метод is_critical корректно определяет критические параметры."""
    base_data = {'ts': datetime.now(), 'pond_id': 'p1', 'user': 'u1'}
    
    # Create a valid object first
    normal_row = WaterQualityRow(**base_data, dissolved_O2_mgL=8, temperature_C=20)
    assert not normal_row.is_critical()

    # --- FIX: Create a valid row, then modify its attribute ---
    row_to_test = WaterQualityRow(**base_data, dissolved_O2_mgL=8, temperature_C=20)
    # Now that the object exists, change the value to something outside the valid range
    row_to_test.dissolved_O2_mgL = settings.DO_MIN - 0.1
    assert row_to_test.is_critical() # Now test the method

    # --- FIX: Do the same for the other test case ---
    row_to_test = WaterQualityRow(**base_data, dissolved_O2_mgL=8, temperature_C=20)
    row_to_test.temperature_C = settings.TEMP_MAX + 0.1
    assert row_to_test.is_critical()

    
def test_water_quality_to_sheet_row():
    """Тест: Метод to_sheet_row для WaterQualityRow формирует корректный список."""
    now = datetime.now()
    # The 'notes' field has a default value, so we don't need to pass it
    row = WaterQualityRow(ts=now, pond_id='P1', dissolved_O2_mgL=7.5, temperature_C=18.2, user='tester')
    sheet_list = row.to_sheet_row()

    assert isinstance(sheet_list, list)
    # FIX: The list should have 6 elements, including the default 'notes'
    assert len(sheet_list) == 6
    assert sheet_list[0] == now.isoformat()
    assert sheet_list[2] == 7.5
    # The 'notes' field will be at index 4, so the 'user' field is at index 5
    assert sheet_list[4] == "" # The default value for notes
    assert sheet_list[5] == 'tester'

  


# --- Тесты для FeedingRow ---

def test_feeding_row_happy_path():
    """Тест: Успешное создание FeedingRow."""
    FeedingRow(ts=datetime.now(), pond_id='p1', feed_type='ft1', mass_kg=10.5, user='u1')

@pytest.mark.parametrize("mass", [0, -10, settings.MAX_FEEDING_MASS_KG + 1])
def test_feeding_row_invalid_mass(mass):
    """Тест: Невалидная масса корма вызывает ValidationError."""
    with pytest.raises(ValidationError, match="Масса корма должна быть в диапазоне"):
        FeedingRow(ts=datetime.now(), pond_id='p1', feed_type='ft1', mass_kg=mass, user='u1')

def test_feeding_row_to_sheet_row():
    """Тест: Метод to_sheet_row для FeedingRow формирует корректный список."""
    now = datetime.now()
    row = FeedingRow(ts=now, pond_id='P2', feed_type='Стартер', mass_kg=5.5, user='tester2')
    sheet_list = row.to_sheet_row()

    assert len(sheet_list) == 5
    assert sheet_list == [now.isoformat(), 'P2', 'Стартер', 5.5, 'tester2']


# --- Тесты для WeighingRow ---

def test_weighing_row_happy_path():
    """Тест: Успешное создание WeighingRow."""
    WeighingRow(ts=datetime.now(), pond_id='p1', avg_weight_g=350.5, user='u1')

@pytest.mark.parametrize("weight", [0, -10, 10001])
def test_weighing_row_invalid_weight(weight):
    """Тест: Невалидный средний вес вызывает ValidationError."""
    with pytest.raises(ValidationError, match="Средний вес должен быть в разумных пределах"):
        WeighingRow(ts=datetime.now(), pond_id='p1', avg_weight_g=weight, user='u1')

def test_weighing_row_to_sheet_row():
    """Тест: Метод to_sheet_row для WeighingRow формирует корректный список."""
    now = datetime.now()
    row = WeighingRow(ts=now, pond_id='P3', avg_weight_g=512.7, user='tester3')
    sheet_list = row.to_sheet_row()

    assert len(sheet_list) == 4
    assert sheet_list == [now.isoformat(), 'P3', 512.7, 'tester3']


# --- Тесты для Pond ---

def test_pond_happy_path():
    """Тест: Успешное создание Pond."""
    Pond(pond_id='P1', name='Pond 1', is_active=True, type='pond', initial_qty=100)

def test_pond_invalid_initial_qty():
    """Тест: Невалидное начальное количество вызывает ValidationError."""
    with pytest.raises(ValidationError):
        Pond(pond_id='P1', name='Pond 1', is_active=True, type='pond', initial_qty=-50)

def test_pond_to_sheet_row():
    """Тест: Метод to_sheet_row для Pond корректно обрабатывает None и даты."""
    today = date.today()
    # Кейс со всеми данными
    pond1 = Pond(pond_id='P1', name='Пруд 1', type='pond', species='Карп',
                 stocking_date=today, initial_qty=1000, notes='Основной', is_active=True)
    sheet_list1 = pond1.to_sheet_row()
    assert len(sheet_list1) == 8
    assert sheet_list1 == ['P1', 'Пруд 1', 'pond', 'Карп', today.isoformat(), 1000, 'Основной', True]

    # Кейс с опциональными полями = None
    pond2 = Pond(pond_id='P2', name='Пруд 2', type='pool', is_active=False)
    sheet_list2 = pond2.to_sheet_row()
    assert len(sheet_list2) == 8
    assert sheet_list2 == ['P2', 'Пруд 2', 'pool', None, None, None, '', False]


# --- Тесты для FishMoveRow ---

def test_fish_move_row_happy_path():
    """Тест: Успешное создание FishMoveRow."""
    FishMoveRow(ts=datetime.now(), pond_id='P1', move_type=FishMoveType.SALE, quantity=100, user='tester')

@pytest.mark.parametrize("quantity", [0, -10])
def test_fish_move_row_invalid_quantity(quantity):
    """Тест: Невалидное количество рыбы вызывает ValidationError."""
    with pytest.raises(ValidationError):
        FishMoveRow(ts=datetime.now(), pond_id='P1', move_type=FishMoveType.SALE, quantity=quantity, user='tester')

def test_fish_move_row_to_sheet_row():
    """Тест: Метод to_sheet_row для FishMoveRow использует Enum.value."""
    now = datetime.now()
    row = FishMoveRow(ts=now, pond_id='P1', move_type=FishMoveType.TRANSFER_OUT,
                      quantity=50, avg_weight_g=150.0, reason='Плановый перевод', user='op1')
    sheet_list = row.to_sheet_row()

    assert len(sheet_list) == 8
    assert sheet_list[2] == "transfer_out" # Проверяем, что Enum преобразован в строку
    assert sheet_list == [now.isoformat(), 'P1', 'transfer_out', 50, 150.0, 'Плановый перевод', None, 'op1']


# --- Тесты для StockMoveRow ---

def test_stock_move_row_happy_path():
    """Тест: Успешное создание StockMoveRow."""
    StockMoveRow(ts=datetime.now(), feed_type_id='F1', feed_type_name='Grower',
                 move_type=StockMoveType.INCOME, mass_kg=500.5, reason='test', user='tester')

@pytest.mark.parametrize("mass", [0, -100.0])
def test_stock_move_row_invalid_mass(mass):
    """Тест: Невалидная масса для складской операции вызывает ValidationError."""
    with pytest.raises(ValidationError):
        StockMoveRow(ts=datetime.now(), feed_type_id='F1', feed_type_name='Grower',
                     move_type=StockMoveType.INCOME, mass_kg=mass, reason='test', user='tester')

def test_stock_move_row_to_sheet_row():
    """Тест: Метод to_sheet_row для StockMoveRow использует Enum.value."""
    now = datetime.now()
    row = StockMoveRow(ts=now, feed_type_id='F-GRW', feed_type_name='Grower 3mm',
                       move_type=StockMoveType.OUTCOME, mass_kg=25.0, reason='Списание', user='sklad')
    sheet_list = row.to_sheet_row()

    assert len(sheet_list) == 7
    assert sheet_list[3] == "outcome" # Проверяем, что Enum преобразован в строку
    assert sheet_list == [now.isoformat(), 'F-GRW', 'Grower 3mm', 'outcome', 25.0, 'Списание', 'sklad']