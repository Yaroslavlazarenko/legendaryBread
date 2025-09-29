# tests/flows/test_operator_flows.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call

from telegram import Update
from telegram.ext import ConversationHandler

from app.flows.operator import (
    State, water_quality_start, pond_selected_for_water, do_received,
    temp_received, save_water_data, feeding_start, pond_selected_for_feeding, 
    feed_type_selected, mass_received_feeding, save_feeding_data, weighing_start, 
    pond_selected_for_weighing, weight_received, save_weighing_data, fish_move_start, 
    pond_src_selected_for_move, move_type_selected, quantity_received_fm, 
    save_fish_move_data, pond_dest_selected_for_move, avg_weight_received_fm, 
    reason_received_fm, ref_received_fm
)
from app.models.pond import Pond
from app.models.user import User
from app.models.feeding import FeedType, FeedingRow
from app.models.weighing import WeighingRow
from app.models.fish import FishMoveType, FishMoveRow
from unittest.mock import ANY # Нужен для сравнения в fish_move_transfer

pytestmark = pytest.mark.asyncio

# --- ОБЩИЕ ФИКСТУРЫ ДЛЯ ВСЕХ ОПЕРАТОРСКИХ СЦЕНАРИЕВ ---

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.callback_query = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {'current_user': User(user_id=456, user_name="Operator", role="operator")}
    context.bot = AsyncMock()
    return context

@pytest.fixture
def mock_pond():
    return Pond(pond_id="P-TEST", name="Тестовый пруд", is_active=True)

# =============================================================
# === Тесты для сценария /water (из test_operator_flow.py) ===
# =============================================================

@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
async def test_water_quality_start_flow(mock_ask_pond, mock_update, mock_context):
    """Тест: полный успешный сценарий замера воды."""
    # Шаг 1: /water
    mock_ask_pond.return_value = True
    next_state = await water_quality_start.__wrapped__(mock_update, mock_context)
    mock_ask_pond.assert_called_once()
    assert next_state == State.SELECT_POND_W

    # Шаг 2: Выбор водоёма
    test_pond = Pond(pond_id="P-TEST", name="Тестовый пруд", is_active=True)
    mock_context.user_data['current_user'] = MagicMock(id=123, name="Tester")
    mock_update.callback_query.data = "pond_P-TEST"
    
    with patch('app.flows.operator.references.get_active_ponds') as mock_get_ponds:
        mock_get_ponds.return_value = [test_pond]
        next_state = await pond_selected_for_water(mock_update, mock_context)

    mock_update.callback_query.edit_message_text.assert_called_with(
        f"Выбран водоём: {test_pond.name}.\n\nВведите значение DO, мг/л (например, 8.5):"
    )
    assert mock_context.user_data['pond'] == test_pond
    assert next_state == State.ENTER_DO

    # Шаг 3: Ввод DO
    mock_update.message.text = "8.5"
    next_state = await do_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("✅ DO принято.\n\nТеперь введите температуру, °C (например, 15.2):")
    assert mock_context.user_data['do'] == 8.5
    assert next_state == State.ENTER_TEMP

    # Шаг 4: Ввод температуры
    mock_update.message.text = "16"
    next_state = await temp_received(mock_update, mock_context)
    assert mock_context.user_data['temp'] == 16.0
    assert next_state == State.CONFIRM_WATER
    assert "Подтвердите данные" in mock_update.message.reply_text.call_args[0][0]
    assert mock_update.message.reply_text.call_args[1]['reply_markup'] is not None

    # Шаг 5: Подтверждение и сохранение
    mock_update.callback_query.data = "confirm_save"
    with patch('app.flows.operator.logs.append_water_quality') as mock_append:
        final_state = await save_water_data(mock_update, mock_context)

    mock_append.assert_called_once()
    mock_update.callback_query.edit_message_text.assert_called_with("✅ Данные успешно сохранены.")
    assert final_state == ConversationHandler.END
    assert not mock_context.user_data.get('pond') # Проверяем, что временные данные удалены

async def test_do_received_invalid_input(mock_update, mock_context):
    """Тест: ввод некорректного DO возвращает на тот же шаг."""
    mock_update.message.text = "не число"
    next_state = await do_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите число (например, 8.5).")
    assert next_state == State.ENTER_DO

# =========================================================================================
# === Тесты для сценариев /feed, /weighing, /fishmove (из test_operator_complex_flows.py) ===
# =========================================================================================

@patch('app.flows.operator.logs')
@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
@patch('app.flows.operator.references')
async def test_feeding_flow_happy_path(mock_references, mock_ask_pond, mock_logs, mock_update, mock_context, mock_pond):
    """Тест 'happy path' для сценария /feed."""
    mock_ask_pond.return_value = True
    mock_feed = FeedType(feed_id='FT1', name='Стартер', is_active=True)
    mock_references.get_active_feed_types.return_value = [mock_feed]
    mock_references.get_active_ponds.return_value = [mock_pond]

    assert await feeding_start.__wrapped__(mock_update, mock_context) == State.SELECT_POND_F
    mock_update.callback_query.data = f"pond_{mock_pond.id}"
    assert await pond_selected_for_feeding(mock_update, mock_context) == State.SELECT_FEED
    mock_update.callback_query.data = f"feed_{mock_feed.id}"
    assert await feed_type_selected(mock_update, mock_context) == State.ENTER_MASS_F
    mock_update.message.text = "25.5"
    assert await mass_received_feeding(mock_update, mock_context) == State.CONFIRM_FEED
    mock_update.callback_query.data = "confirm_save"
    final_state = await save_feeding_data(mock_update, mock_context)

    mock_logs.append_feeding.assert_called_once()
    saved_row: FeedingRow = mock_logs.append_feeding.call_args[0][0]
    assert saved_row.pond_id == mock_pond.id
    assert saved_row.mass_kg == 25.5
    assert final_state == ConversationHandler.END

@patch('app.flows.operator.logs')
@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
@patch('app.flows.operator.references.get_active_ponds')
async def test_weighing_flow_happy_path(mock_get_ponds, mock_ask_pond, mock_logs, mock_update, mock_context, mock_pond):
    """Тест 'happy path' для сценария /weighing."""
    mock_ask_pond.return_value = True
    mock_get_ponds.return_value = [mock_pond]
    
    assert await weighing_start.__wrapped__(mock_update, mock_context) == State.SELECT_POND_WGH
    mock_update.callback_query.data = f"pond_{mock_pond.id}"
    assert await pond_selected_for_weighing(mock_update, mock_context) == State.ENTER_WEIGHT
    mock_update.message.text = "350.5"
    assert await weight_received(mock_update, mock_context) == State.CONFIRM_WEIGHING
    mock_update.callback_query.data = "confirm_save"
    final_state = await save_weighing_data(mock_update, mock_context)

    mock_logs.append_weighing.assert_called_once()
    saved_row: WeighingRow = mock_logs.append_weighing.call_args[0][0]
    assert saved_row.avg_weight_g == 350.5
    assert final_state == ConversationHandler.END

@patch('app.flows.operator.logs')
@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
@patch('app.flows.operator.references.get_active_ponds')
async def test_fish_move_sale_flow(mock_get_ponds, mock_ask_pond, mock_logs, mock_update, mock_context, mock_pond):
    """Тест 'happy path' для /fishmove, ветка 'Продажа'."""
    mock_ask_pond.return_value = True
    mock_get_ponds.return_value = [mock_pond]
    
    await fish_move_start(mock_update, mock_context)
    mock_update.callback_query.data = f"pond_{mock_pond.id}"
    await pond_src_selected_for_move(mock_update, mock_context)
    mock_update.callback_query.data = f"move_{FishMoveType.SALE.value}"
    assert await move_type_selected(mock_update, mock_context) == State.ENTER_QUANTITY_FM
    mock_update.message.text = "100"
    assert await quantity_received_fm(mock_update, mock_context) == State.ENTER_AVG_WEIGHT_FM
    mock_update.message.text = "450"
    assert await avg_weight_received_fm(mock_update, mock_context) == State.ENTER_REASON_FM
    mock_update.message.text = "Продажа клиенту"
    assert await reason_received_fm(mock_update, mock_context) == State.ENTER_REF_FM
    mock_update.message.text = "Заказ #123"
    assert await ref_received_fm(mock_update, mock_context) == State.CONFIRM_FISH_MOVE
    mock_update.callback_query.data = "confirm_save"
    await save_fish_move_data(mock_update, mock_context)

    mock_logs.append_fish_move.assert_called_once()
    saved_row: FishMoveRow = mock_logs.append_fish_move.call_args[0][0]
    assert saved_row.move_type == FishMoveType.SALE
    assert saved_row.quantity == 100
    assert saved_row.avg_weight_g == 450
    assert saved_row.reason == "Продажа клиенту"
    assert saved_row.ref == "Заказ #123"

@patch('app.flows.operator.logs')
@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
@patch('app.flows.operator.references.get_active_ponds')
async def test_fish_move_stocking_flow(mock_get_ponds, mock_ask_pond, mock_logs, mock_update, mock_context, mock_pond):
    """Тест 'happy path' для /fishmove, ветка 'Зарыбление'."""
    mock_ask_pond.return_value = True
    mock_get_ponds.return_value = [mock_pond]
    
    await fish_move_start(mock_update, mock_context)
    mock_update.callback_query.data = f"pond_{mock_pond.id}"
    await pond_src_selected_for_move(mock_update, mock_context)
    mock_update.callback_query.data = f"move_{FishMoveType.STOCKING.value}"
    await move_type_selected(mock_update, mock_context)

    assert 'pond_src' not in mock_context.user_data
    assert mock_context.user_data['pond_dest'] == mock_pond
    
    mock_update.message.text = "5000"
    await quantity_received_fm(mock_update, mock_context)
    mock_update.message.text = "0"
    await avg_weight_received_fm(mock_update, mock_context)
    mock_update.message.text = "Закупка малька"
    await reason_received_fm(mock_update, mock_context)
    mock_update.message.text = "нет"
    await ref_received_fm(mock_update, mock_context)
    mock_update.callback_query.data = "confirm_save"
    await save_fish_move_data(mock_update, mock_context)
    
    mock_logs.append_fish_move.assert_called_once()
    saved_row: FishMoveRow = mock_logs.append_fish_move.call_args[0][0]
    assert saved_row.move_type == FishMoveType.STOCKING
    assert saved_row.quantity == 5000

@patch('app.flows.operator.logs')
@patch('app.flows.operator.ask_for_pond_selection', new_callable=AsyncMock)
@patch('app.flows.operator.references.get_active_ponds')
async def test_fish_move_transfer_flow(mock_get_ponds, mock_ask_pond, mock_logs, mock_update, mock_context):
    """Тест 'happy path' для /fishmove, ветка 'Перевод'."""
    pond_src = Pond(pond_id="P-SRC", name="Источник", is_active=True)
    pond_dest = Pond(pond_id="P-DEST", name="Получатель", is_active=True)
    mock_ask_pond.return_value = True
    mock_get_ponds.return_value = [pond_src, pond_dest]
    
    # --- FIX: Call the wrapped function ---
    await fish_move_start.__wrapped__(mock_update, mock_context)
    
    # ... (rest of the flow execution is the same)
    mock_update.callback_query.data = f"pond_{pond_src.id}"
    await pond_src_selected_for_move(mock_update, mock_context)
    mock_update.callback_query.data = "move_transfer"
    mock_get_ponds.return_value = [pond_dest]
    await move_type_selected(mock_update, mock_context)
    mock_update.callback_query.data = f"ponddest_{pond_dest.id}"
    await pond_dest_selected_for_move(mock_update, mock_context)
    
    mock_update.message.text = "250"
    await quantity_received_fm(mock_update, mock_context)
    mock_update.message.text = "300"
    await avg_weight_received_fm(mock_update, mock_context)
    mock_update.message.text = "Плановая сортировка"
    await reason_received_fm(mock_update, mock_context)
    mock_update.message.text = "Акт #42"
    await ref_received_fm(mock_update, mock_context)
    mock_update.callback_query.data = "confirm_save"
    await save_fish_move_data(mock_update, mock_context)

    assert mock_logs.append_fish_move.call_count == 2
    calls = mock_logs.append_fish_move.call_args_list
    
    # --- FIX: Define expected values as dictionaries, not Pydantic models ---
    row_out_expected_dict = {
        'pond_id': pond_src.id, 
        'move_type': FishMoveType.TRANSFER_OUT, 
        'quantity': 250, 
        'avg_weight_g': 300, 
        'reason': 'Плановая сортировка', 
        'ref': 'Акт #42'
    }
    row_in_expected_dict = {
        'pond_id': pond_dest.id, 
        'move_type': FishMoveType.TRANSFER_IN, 
        'quantity': 250, 
        'avg_weight_g': 300, 
        'reason': 'Плановая сортировка', 
        'ref': 'Акт #42'
    }
    
    row_out_actual: FishMoveRow = calls[0].args[0]
    row_in_actual: FishMoveRow = calls[1].args[0]

    # --- FIX: Compare the actual model dump with the expected dictionary ---
    assert row_out_actual.model_dump(exclude={'ts', 'user'}) == row_out_expected_dict
    assert row_in_actual.model_dump(exclude={'ts', 'user'}) == row_in_expected_dict