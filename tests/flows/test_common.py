import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import ConversationHandler
from app.flows.common import cancel, ask_for_pond_selection
from app.models.user import User
from app.models.pond import Pond

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = AsyncMock()
    update.callback_query = None # По умолчанию
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {'current_user': User(user_id=123, user_name="test", role="admin"), 'some_data': 'to_be_cleared'}
    return context

async def test_cancel_from_message(mock_update, mock_context):
    """Тест: отмена диалога через команду /cancel."""
    result = await cancel(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_with("Действие отменено.")
    assert result == ConversationHandler.END
    # Проверяем, что временные данные удалены, а сессия пользователя сохранена
    assert 'some_data' not in mock_context.user_data
    assert 'current_user' in mock_context.user_data

async def test_cancel_from_callback(mock_update, mock_context):
    """Тест: отмена диалога через inline-кнопку."""
    mock_update.callback_query = AsyncMock()
    mock_update.message = None # Имитируем, что это callback

    result = await cancel(mock_update, mock_context)

    mock_update.callback_query.edit_message_text.assert_called_with("Действие отменено.")
    assert result == ConversationHandler.END
    assert 'some_data' not in mock_context.user_data
    assert 'current_user' in mock_context.user_data

@patch('app.flows.common.references')
async def test_ask_for_pond_selection_with_ponds(mock_references, mock_update):
    """Тест: функция выбора водоема, когда водоемы существуют."""
    mock_ponds = [Pond(pond_id='P1', name='Pond One', is_active=True)]
    mock_references.get_active_ponds.return_value = mock_ponds

    result = await ask_for_pond_selection(mock_update, "Select a pond:")

    assert result is True
    mock_update.message.reply_text.assert_called_once()
    # Проверяем, что в сообщении есть клавиатура
    assert 'reply_markup' in mock_update.message.reply_text.call_args.kwargs

@patch('app.flows.common.references')
async def test_ask_for_pond_selection_no_ponds(mock_references, mock_update):
    """Тест: функция выбора водоема, когда нет активных водоемов."""
    mock_references.get_active_ponds.return_value = []

    result = await ask_for_pond_selection(mock_update, "Select a pond:")

    assert result is False
    mock_update.message.reply_text.assert_called_with(
        "В системе нет активных водоёмов. Обратитесь к администратору, чтобы добавить или активировать их."
    )