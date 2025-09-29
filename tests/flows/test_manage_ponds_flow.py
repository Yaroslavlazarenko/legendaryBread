import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from app.flows.manage_ponds import (
    PondState, ponds_start, add_pond_start, add_name_received, add_type_received,
    add_species_received, add_stocking_date_received, add_initial_qty_received,
    add_notes_received, save_new_pond, select_pond_for_action, toggle_pond_status,
    edit_pond_data_start, ask_for_new_field_value, receive_and_update_field_value
)
from app.models.pond import Pond

# Указываем, что все тесты в этом файле асинхронные
pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_update():
    """Более надежная фикстура для мока Update."""
    update = MagicMock()
    # Методы, которые вызываются через await, делаем AsyncMock
    update.message.reply_text = AsyncMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    return context

# --- Тест "happy path" для добавления водоёма ---
@patch('app.flows.manage_ponds.logs')
@patch('app.flows.manage_ponds.references')
async def test_add_pond_full_happy_path(mock_references, mock_logs, mock_update, mock_context):
    """Тест полного успешного сценария добавления нового водоёма."""
    # --- Шаг 1: /manage_ponds -> нажимаем "Добавить"
    mock_update.callback_query.data = "add_new"
    await add_pond_start(mock_update, mock_context)
    assert 'new_pond_data' in mock_context.user_data
    # ИСПРАВЛЕНО: Проверяем ключ 'pond_id'
    assert mock_context.user_data['new_pond_data']['pond_id'].startswith("POND-")
    
    # --- Шаги 2-7: Последовательно вводим все данные
    mock_update.message.text = "Тестовый Пруд"
    await add_name_received(mock_update, mock_context)
    
    mock_update.callback_query.data = "type_pond"
    await add_type_received(mock_update, mock_context)
    
    mock_update.message.text = "Карп"
    await add_species_received(mock_update, mock_context)
    
    mock_update.message.text = "2023-05-10"
    await add_stocking_date_received(mock_update, mock_context)
    
    mock_update.message.text = "5000"
    await add_initial_qty_received(mock_update, mock_context)

    mock_update.message.text = "Заметка"
    next_state = await add_notes_received(mock_update, mock_context)
    
    # Assert: Проверяем, что дошли до подтверждения и данные корректны
    assert next_state == PondState.CONFIRM_ADD
    data = mock_context.user_data['new_pond_data']
    assert data['name'] == "Тестовый Пруд"
    assert data['type'] == "pond"
    assert data['species'] == "Карп"
    assert data['stocking_date'] == date(2023, 5, 10)
    assert data['initial_qty'] == 5000
    assert data['notes'] == "Заметка"

    # --- Шаг 8: Сохранение
    mock_update.callback_query.data = "save_new"
    mock_references.get_all_ponds.return_value = []
    # ИСПРАВЛЕНО: save_new_pond вызывает ponds_start, его нужно мокать, чтобы проверить возвращаемое состояние
    with patch('app.flows.manage_ponds.ponds_start', new_callable=AsyncMock) as mock_ponds_start:
        mock_ponds_start.return_value = PondState.MENU
        final_state = await save_new_pond(mock_update, mock_context)

    # Assert: Проверяем, что лог был вызван и данные очищены
    mock_logs.append_pond.assert_called_once()
    saved_pond: Pond = mock_logs.append_pond.call_args[0][0]
    assert saved_pond.name == "Тестовый Пруд"
    assert 'new_pond_data' not in mock_context.user_data
    assert final_state == PondState.MENU

# --- Тесты для некорректного ввода при добавлении ---
async def test_add_pond_invalid_date_format(mock_update, mock_context):
    """Тест: ввод даты зарыбления в неверном формате."""
    mock_update.message.text = "25-12-2023"
    next_state = await add_stocking_date_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат даты. Используйте ГГГГ-ММ-ДД или 'нет'.")
    assert next_state == PondState.ADD_STOCKING_DATE

async def test_add_pond_invalid_initial_qty(mock_update, mock_context):
    """Тест: ввод некорректного начального количества рыбы."""
    mock_update.message.text = "не число"
    next_state = await add_initial_qty_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите целое положительное число или 'нет'.")
    assert next_state == PondState.ADD_INITIAL_QTY

async def test_add_pond_negative_initial_qty(mock_update, mock_context):
    """Тест: ввод отрицательного начального количества рыбы."""
    mock_update.message.text = "-100"
    next_state = await add_initial_qty_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите целое положительное число или 'нет'.")
    assert next_state == PondState.ADD_INITIAL_QTY

# --- Тесты для управления существующими водоёмами ---
@patch('app.flows.manage_ponds.ponds_start', new_callable=AsyncMock)
@patch('app.flows.manage_ponds.references')
async def test_toggle_pond_status_flow(mock_references, mock_ponds_start, mock_update, mock_context):
    """Тест сценария смены статуса активности водоема."""
    pond_id = "POND-TOGGLE"
    # ИСПРАВЛЕНО: Создаем Pond с pond_id и всеми обязательными полями
    mock_pond = Pond(pond_id=pond_id, name="Тестовый", type="pond", is_active=False)
    mock_context.user_data['selected_pond_id'] = pond_id
    mock_references.get_pond_by_id.return_value = mock_pond
    mock_references.update_pond_status.return_value = True

    await toggle_pond_status(mock_update, mock_context)
    
    mock_references.update_pond_status.assert_called_once_with(pond_id, True) # Был False, станет True
    mock_update.callback_query.edit_message_text.assert_called_with("✅ Статус водоёма успешно изменен.")
    mock_ponds_start.assert_called_once_with(mock_update, mock_context)
    
@patch('app.flows.manage_ponds._display_pond_actions', new_callable=AsyncMock)
@patch('app.flows.manage_ponds.references')
async def test_edit_pond_name_flow(mock_references, mock_display_actions, mock_update, mock_context):
    """Тест сценария редактирования названия водоема."""
    pond_id = "POND-EDIT"
    # ИСПРАВЛЕНО: Создаем Pond с pond_id и всеми обязательными полями
    mock_pond = Pond(pond_id=pond_id, name="Старое Название", type="pond", is_active=True)
    mock_references.get_pond_by_id.return_value = mock_pond
    mock_references.update_pond_details.return_value = True
    
    # Симулируем, что мы на шаге ввода нового значения
    mock_context.user_data['selected_pond_id'] = pond_id
    mock_context.user_data['edit_field_name'] = 'name'
    mock_update.message.text = "Новое Название Пруда"
    # ИСПРАВЛЕНО: Явно указываем, что это текстовое сообщение, а не callback_query
    mock_update.callback_query = None

    # Мокаем конечную точку, чтобы проверить результат
    mock_display_actions.return_value = PondState.SELECT_ACTION
    next_state = await receive_and_update_field_value(mock_update, mock_context)
    
    # Assert
    mock_references.update_pond_details.assert_called_once_with(pond_id, 'name', "Новое Название Пруда")
    mock_update.message.reply_text.assert_called_with("✅ Поле 'name' успешно обновлено.")
    # Проверяем, что вернулись в меню действий
    mock_display_actions.assert_called_once_with(pond_id, mock_update, mock_context)
    assert next_state == PondState.SELECT_ACTION

@patch('app.flows.manage_ponds.references')
async def test_edit_pond_invalid_value(mock_references, mock_update, mock_context):
    """Тест: ввод неверного значения при редактировании (например, дата)."""
    # Arrange: Симулируем, что мы на шаге ввода нового значения
    pond_id = "POND-EDIT"
    mock_context.user_data['selected_pond_id'] = pond_id
    mock_context.user_data['edit_field_name'] = 'initial_qty'
    
    # Act: Вводим текст вместо числа
    mock_update.message.text = "много рыбы"
    # ИСПРАВЛЕНО: Явно указываем, что это текстовое сообщение
    mock_update.callback_query = None
    
    await receive_and_update_field_value(mock_update, mock_context)
    
    # Assert
    mock_references.update_pond_details.assert_not_called()
    mock_update.message.reply_text.assert_called_once()
    assert "❗️Неверный формат или значение" in mock_update.message.reply_text.call_args[0][0]