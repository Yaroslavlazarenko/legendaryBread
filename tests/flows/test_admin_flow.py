import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from telegram import Update

# Import the original, undecorated function for testing
from app.flows.admin import (
    admin_panel_start, AdminState, show_user_menu, show_user_list,
    show_user_actions, ask_for_role_change, update_user_role,
    show_new_orders, show_order_details, change_order_status
)
from app.models.user import User, UserRole
# Import create_main_menu_keyboard for assertion, or patch it. Patching is generally preferred.
# from app.bot.keyboards import create_main_menu_keyboard

pytestmark = pytest.mark.asyncio

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
    # Initialize with the required field ALIASES 'user_id' and 'user_name'
    admin_user = User(user_id=123, user_name="Admin", role=UserRole.ADMIN)
    context.user_data = {'current_user': admin_user}
    context.bot = AsyncMock()
    return context

@patch('app.flows.admin.references')
async def test_admin_user_management_flow(mock_references, mock_update, mock_context):
    """Тест: 'happy path' сценария смены роли пользователя (ОБНОВЛЕННЫЙ)."""

    # --- Шаг 1: /admin -> admin_panel_start ---
    mock_update.callback_query = None
    undecorated_start = admin_panel_start.__wrapped__
    next_state = await undecorated_start(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("Панель администратора:", reply_markup=ANY)
    assert next_state == AdminState.ADMIN_MENU

    # Restore callback_query
    mock_update.callback_query = AsyncMock()

    # --- Шаг 2: Нажатие "Управление пользователями" -> show_user_menu ---
    mock_update.callback_query.data = "goto_users"
    next_state = await show_user_menu(mock_update, mock_context)
    mock_update.callback_query.edit_message_text.assert_called_with("Управление пользователями:", reply_markup=ANY)
    assert next_state == AdminState.USER_MENU

    # --- Шаг 3: Нажатие "Управлять существующими" -> show_user_list ---
    mock_user = User(user_id=456, user_name="Test User", role=UserRole.CLIENT)
    mock_references.get_all_users.return_value = [mock_user]
    mock_update.callback_query.data = "users_manage"
    
    with patch('app.flows.admin.create_paginated_keyboard', return_value=MagicMock()) as mock_create_keyboard:
        next_state = await show_user_list(mock_update, mock_context)

    mock_references.get_all_users.assert_called_once()
    mock_create_keyboard.assert_called_once()
    mock_update.callback_query.edit_message_text.assert_called_with("Выберите пользователя для управления:", reply_markup=ANY)
    assert next_state == AdminState.USER_LIST

    # --- Шаг 4: Выбор пользователя -> show_user_actions ---
    mock_references.get_user_by_id.return_value = mock_user
    mock_update.callback_query.data = "user_456"
    next_state = await show_user_actions(mock_update, mock_context)
    
    mock_references.get_user_by_id.assert_called_with(456)
    assert f"Управление: {mock_user.name}" in mock_update.callback_query.edit_message_text.call_args[0][0]
    assert mock_context.user_data['selected_user_id'] == 456
    assert next_state == AdminState.USER_ACTIONS

    # --- Шаг 5: Нажатие "Сменить роль" -> ask_for_role_change ---
    mock_references.get_user_by_id.return_value = mock_user # This mock is still needed here
    mock_update.callback_query.data = "action_changerole"
    next_state = await ask_for_role_change(mock_update, mock_context)

    mock_update.callback_query.edit_message_text.assert_called_with(
        f"Выберите новую роль для {mock_user.name}:",
        reply_markup=ANY
    )
    assert next_state == AdminState.SELECT_ROLE

    # --- Шаг 6: Выбор новой роли -> update_user_role ---

    # 1. ARRANGE: Set up the return values for the mocks used inside update_user_role
    mock_references.update_user_role.return_value = True
    updated_user = User(user_id=456, user_name="Test User", role=UserRole.OPERATOR)
    mock_references.get_user_by_id.return_value = updated_user
    mock_update.callback_query.data = "role_operator"

    # Define the expected message text
    expected_user_message_text = (
        f"Ваша учетная запись обновлена! ✨\n\n"
        f"Ваша новая роль: <b>{UserRole.OPERATOR.value}</b>.\n\n"
        f"Используйте меню ниже для навигации."
    )

    # 2. ACT: Call the function we want to test with patch for create_main_menu_keyboard
    with patch('app.flows.admin.create_main_menu_keyboard', return_value=MagicMock()) as mock_create_keyboard_func:
        next_state = await update_user_role(mock_update, mock_context)

        # 3. ASSERT: Now, check the results of the call
        assert next_state == AdminState.USER_ACTIONS

        # Assert that the user was notified with the correct message and markup
        mock_context.bot.send_message.assert_called_once_with(
            chat_id=456, 
            text=expected_user_message_text,
            reply_markup=ANY, # create_main_menu_keyboard returns a MagicMock, so ANY is appropriate
            parse_mode='HTML'
        )
        # Assert that create_main_menu_keyboard was called correctly
        mock_create_keyboard_func.assert_called_once_with(UserRole.OPERATOR)

    # Assert the database/sheets function was called correctly
    mock_references.update_user_role.assert_called_with(456, UserRole.OPERATOR)
    
    # Assert that the temporary success message was shown
    mock_update.callback_query.edit_message_text.assert_any_call(
        f"✅ Пользователю {updated_user.name} назначена роль: {updated_user.role.value}"
    )

    # Assert that the final message is the refreshed user actions menu
    mock_update.callback_query.edit_message_text.assert_called_with(
        f"Управление: {updated_user.name}\nТекущая роль: {updated_user.role.value}",
        reply_markup=ANY
    )


# --- No changes needed for the other tests' setup, only object attribute and final state ---
@patch('app.flows.admin.create_paginated_keyboard', return_value=MagicMock())
@patch('app.flows.admin.references.get_all_users')
async def test_admin_flow_back_from_user_actions(mock_get_users, mock_create_keyboard, mock_update, mock_context):
    mock_get_users.return_value = []
    mock_context.user_data['user_list_type'] = 'manage'
    mock_update.callback_query.data = "users_manage_page_0"
    next_state = await show_user_list(mock_update, mock_context)
    mock_get_users.assert_called_once()
    mock_create_keyboard.assert_called_once()
    mock_update.callback_query.edit_message_text.assert_called_with("Нет зарегистрированных пользователей.", reply_markup=ANY)
    assert next_state == AdminState.USER_LIST

@patch('app.flows.admin.references')
async def test_admin_order_management_flow(mock_references, mock_update, mock_context):
    order_id = "ORD-12345-678"
    # FIX: Change 'order_id' attribute to 'id' to match how it's accessed in show_order_details
    mock_order = MagicMock(id=order_id, client_id=999, client_name="Test Client", total_amount=500.0, phone="12345")
    mock_order_item = MagicMock(product_name="Карп", quantity=5, price_per_unit=100.0)
    mock_references.get_orders_by_status.return_value = [mock_order]
    mock_references.get_all_orders.return_value = [mock_order] # Make sure order is found here
    mock_references.get_order_items.return_value = [mock_order_item]
    mock_references.update_order_status.return_value = True
    mock_update.callback_query.data = "goto_orders"
    next_state = await show_new_orders(mock_update, mock_context)
    assert next_state == AdminState.ORDER_LIST
    mock_update.callback_query.edit_message_text.assert_called_with("Новые заказы:", reply_markup=ANY)
    mock_update.callback_query.data = f"order_{order_id}"
    next_state = await show_order_details(mock_update, mock_context)
    assert next_state == AdminState.ORDER_DETAILS # This assertion should now pass
    assert mock_context.user_data['selected_order_id'] == order_id
    mock_references.get_order_items.assert_called_with(order_id)
    mock_update.callback_query.data = "status_confirmed"
    mock_references.get_orders_by_status.return_value = [] # No new orders after confirmation
    next_state = await change_order_status(mock_update, mock_context)
    mock_references.update_order_status.assert_called_with(order_id, "confirmed")
    mock_context.bot.send_message.assert_called_once()
    # FIX: Final state should be ADMIN_MENU if no new orders are left
    assert next_state == AdminState.ADMIN_MENU 

@patch('app.flows.admin.references')
async def test_admin_order_cancellation_flow(mock_references, mock_update, mock_context):
    order_id = "ORD-CANCEL-123"
    # FIX: Change 'order_id' attribute to 'id' to match how it's accessed in change_order_status
    mock_order = MagicMock(id=order_id, client_id=999, client_name="Test Client")
    mock_references.get_all_orders.return_value = [mock_order] # Make sure order is found here
    mock_references.get_orders_by_status.return_value = [] # No new orders after cancellation
    mock_references.update_order_status.return_value = True
    mock_context.user_data['selected_order_id'] = order_id
    mock_update.callback_query.data = "status_cancelled"
    next_state = await change_order_status(mock_update, mock_context)
    mock_references.update_order_status.assert_called_with(order_id, "cancelled")
    mock_context.bot.send_message.assert_called_once()
    assert "<b>отменен</b>" in mock_context.bot.send_message.call_args.kwargs['text']
    # FIX: Final state should be ADMIN_MENU if no new orders are left
    assert next_state == AdminState.ADMIN_MENU