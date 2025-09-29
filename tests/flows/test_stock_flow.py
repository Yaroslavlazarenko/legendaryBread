import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from telegram.ext import ConversationHandler
from app.flows.stock import (
    StockState, stock_start, feed_selected, type_selected, mass_received, reason_received, save_stock_move
)
from app.models.feeding import FeedType
from app.models.stock import StockMoveType
from app.models.user import User

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = AsyncMock()
    update.callback_query = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    # FIX: Initialize the User model using its field aliases ('user_id', 'user_name')
    context.user_data = {'current_user': User(user_id=123, user_name="Admin", role="admin")}
    return context

@pytest.fixture
def mock_feed_type():
    return FeedType(feed_id="FT-GROWER", name="Grower Feed", is_active=True)

@patch('app.flows.stock.references')
@patch('app.flows.stock.logs')
async def test_stock_full_flow(mock_logs, mock_references, mock_update, mock_context, mock_feed_type):
    """Тест полного сценария складской операции (приход)."""
    
    mock_references.get_active_feed_types.return_value = [mock_feed_type]

    # --- Шаг 1: /stock -> stock_start
    next_state = await stock_start.__wrapped__(mock_update, mock_context)
    assert next_state == StockState.SELECT_FEED
    
    # FIX: Use ANY to verify that some reply_markup was passed
    mock_update.message.reply_text.assert_called_with(
        "Выберите тип корма для складской операции:", 
        reply_markup=ANY
    )

    # --- Шаг 2: Выбор корма -> feed_selected
    mock_update.callback_query.data = "feed_FT-GROWER"
    next_state = await feed_selected(mock_update, mock_context)
    assert next_state == StockState.SELECT_TYPE
    assert mock_context.user_data['stock_feed'] == mock_feed_type

    # --- Шаг 3: Выбор типа операции -> type_selected
    mock_update.callback_query.data = f"type_{StockMoveType.INCOME.value}"
    next_state = await type_selected(mock_update, mock_context)
    assert next_state == StockState.ENTER_MASS
    assert mock_context.user_data['stock_move_type'] == StockMoveType.INCOME

    # --- Шаг 4: Ввод массы -> mass_received
    mock_update.message.text = "1250.5"
    next_state = await mass_received(mock_update, mock_context)
    assert next_state == StockState.ENTER_REASON
    assert mock_context.user_data['stock_mass'] == 1250.5

    # --- Шаг 5: Ввод причины -> reason_received
    mock_update.message.text = "Закупка по накладной #123"
    next_state = await reason_received(mock_update, mock_context)
    assert next_state == StockState.CONFIRM
    assert mock_context.user_data['stock_reason'] == "Закупка по накладной #123"
    assert "Подтвердите операцию" in mock_update.message.reply_text.call_args.args[0]

    # --- Шаг 6: Подтверждение -> save_stock_move
    mock_update.callback_query.data = "save"
    final_state = await save_stock_move(mock_update, mock_context)
    assert final_state == ConversationHandler.END

    # Проверяем, что данные были отправлены в лог
    mock_logs.append_stock_move.assert_called_once()
    saved_row = mock_logs.append_stock_move.call_args[0][0]
    assert saved_row.feed_type_id == "FT-GROWER"
    assert saved_row.move_type == StockMoveType.INCOME
    assert saved_row.mass_kg == 1250.5