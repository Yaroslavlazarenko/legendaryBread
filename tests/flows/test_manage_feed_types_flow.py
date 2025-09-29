import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.flows.manage_feed_types import (
    FeedState, feed_types_start, add_feed_type_start, add_feed_name_received,
    save_new_feed_type, select_feed_type_for_action, toggle_feed_type_status,
    ask_for_new_name, save_new_name
)
from app.models.feeding import FeedType

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
    context.user_data = {}
    return context

@patch('app.flows.manage_feed_types.feed_types_start', new_callable=AsyncMock)
@patch('app.flows.manage_feed_types.references')
@patch('app.flows.manage_feed_types.logs')
async def test_add_feed_type_happy_path(mock_logs, mock_references, mock_feed_start, mock_update, mock_context):
    """Тест 'happy path' для добавления нового типа корма."""
    # --- Шаг 1: /manage_feed_types, затем нажимаем "Добавить"
    mock_update.callback_query.data = "add_new"
    mock_references.get_feed_types.return_value = []
    # Для начала надо попасть в меню
    # Мы не проверяем здесь состояние, т.к. save_new_feed_type вызовет эту функцию снова
    await feed_types_start(mock_update, mock_context)

    # Теперь симулируем нажатие кнопки "Добавить"
    assert await add_feed_type_start(mock_update, mock_context) == FeedState.ADD_NAME
    mock_update.callback_query.edit_message_text.assert_called_with("Введите название нового типа корма:")

    # --- Шаг 2: Вводим название
    mock_update.message.text = "Новый корм"
    assert await add_feed_name_received(mock_update, mock_context) == FeedState.CONFIRM_ADD
    assert mock_context.user_data['new_feed_type_data']['name'] == "Новый корм"

    # --- Шаг 3: Подтверждаем сохранение
    mock_update.callback_query.data = "save_new"
    # Мокаем get_feed_types еще раз, т.к. он вызывается при возврате в меню
    mock_references.get_feed_types.return_value = [FeedType(feed_id='...', name='Новый корм', is_active=True)]
    
    # Управляем возвращаемым значением замоканной функции
    mock_feed_start.return_value = FeedState.MENU

    # save_new_feed_type теперь вызывает feed_types_start, который возвращает FeedState.MENU
    final_state = await save_new_feed_type(mock_update, mock_context)
    assert final_state == FeedState.MENU

    # Проверяем, что данные были отправлены на запись
    mock_logs.append_feed_type.assert_called_once()
    saved_feed_type: FeedType = mock_logs.append_feed_type.call_args[0][0]
    assert saved_feed_type.name == "Новый корм"
    # Проверяем, что временные данные удалены
    assert 'new_feed_type_data' not in mock_context.user_data
    # Проверяем, что был вызван переход в главное меню
    mock_feed_start.assert_called_once_with(mock_update, mock_context)


@patch('app.flows.manage_feed_types.feed_types_start', new_callable=AsyncMock)
@patch('app.flows.manage_feed_types.references')
async def test_toggle_feed_type_status_flow(mock_references, mock_feed_start, mock_update, mock_context):
    """Тест сценария смены статуса активности типа корма."""
    # Arrange
    feed_id = "FT-TOGGLE"
    mock_feed = FeedType(feed_id=feed_id, name="Тестовый", is_active=True)
    mock_context.user_data['selected_feed_type_id'] = feed_id
    mock_references.get_feed_type_by_id.return_value = mock_feed
    mock_references.update_feed_type_status.return_value = True

    # Act: Нажимаем кнопку смены статуса
    mock_update.callback_query.data = "toggle_status"
    await toggle_feed_type_status(mock_update, mock_context)

    # Assert
    mock_references.update_feed_type_status.assert_called_once_with(feed_id, False) # Был True, станет False
    mock_update.callback_query.edit_message_text.assert_called_with("✅ Статус успешно изменен.")

    # Проверяем, что в конце был вызван возврат в главное меню
    mock_feed_start.assert_called_once_with(mock_update, mock_context)


@patch('app.flows.manage_feed_types.references')
async def test_edit_feed_type_name_flow(mock_references, mock_update, mock_context):
    """Тест сценария редактирования названия типа корма."""
    # Arrange
    feed_id = "FT-EDIT"
    mock_feed = FeedType(feed_id=feed_id, name="Старое Имя", is_active=True)
    mock_references.get_feed_type_by_id.return_value = mock_feed
    mock_references.update_feed_type_details.return_value = True

    # --- Шаг 1: Выбираем тип корма
    mock_update.callback_query.data = f"select_{feed_id}"
    next_state = await select_feed_type_for_action(mock_update, mock_context)
    assert next_state == FeedState.SELECT_ACTION # Проверяем, что попали в меню действий

    # --- Шаг 2: Нажимаем "Редактировать название"
    mock_update.callback_query.data = "edit_name"
    next_state = await ask_for_new_name(mock_update, mock_context)
    assert next_state == FeedState.EDIT_NAME

    # --- Шаг 3: Вводим новое имя
    mock_update.message.text = "Новое Имя"
    # get_feed_type_by_id будет вызван снова внутри _display_feed_type_actions
    mock_feed.name = "Новое Имя"
    mock_references.get_feed_type_by_id.return_value = mock_feed

    mock_update.callback_query = None

    next_state = await save_new_name(mock_update, mock_context)

    # Assert
    mock_references.update_feed_type_details.assert_called_once_with(feed_id, 'name', "Новое Имя")
    mock_update.message.reply_text.assert_any_call("✅ Название обновлено.")

    # Проверяем, что мы вернулись в меню действий, и бот обновил сообщение
    assert "<b>Тип корма:</b> Новое Имя" in mock_update.message.reply_text.call_args.args[0]
    assert next_state == FeedState.SELECT_ACTION


@patch('app.flows.manage_feed_types.feed_types_start', new_callable=AsyncMock)
@patch('app.flows.manage_feed_types.references')
async def test_action_on_nonexistent_feed_type(mock_references, mock_feed_start, mock_update, mock_context):
    """Тест: Попытка выполнить действие с несуществующим типом корма."""
    # Arrange
    feed_id = "FT-NONEXISTENT"
    mock_references.get_feed_type_by_id.return_value = None # Симулируем, что корм удалили
    mock_context.user_data['selected_feed_type_id'] = feed_id

    # Act: Пытаемся переключить статус
    await toggle_feed_type_status(mock_update, mock_context)

    # Assert
    # Проверяем, что была попытка получить тип корма
    mock_references.get_feed_type_by_id.assert_called_once_with(feed_id)
    # Проверяем, что не было попытки обновить статус
    mock_references.update_feed_type_status.assert_not_called()
    # Проверяем сообщение об ошибке
    mock_update.callback_query.edit_message_text.assert_called_with("❌ Ошибка: тип корма не найден.")
    # Проверяем, что произошел безопасный возврат в главное меню
    mock_feed_start.assert_called_once_with(mock_update, mock_context, clear_selection=True)