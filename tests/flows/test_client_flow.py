import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from telegram import InlineKeyboardMarkup
from telegram.ext import ConversationHandler

from app.flows.client import (
    OrderState, order_start, product_selected_for_order, quantity_received, 
    show_cart_and_confirm, finalize_order
)
from app.models.product import Product
from app.models.user import User, UserRole
from app.models.order import SalesOrderRow, SalesOrderItemRow

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_update():
    update = MagicMock()
    update.message = AsyncMock()
    update.callback_query = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 789
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {
        'current_user': User(user_id=789, user_name="Client Test", phone="555-123", role=UserRole.CLIENT)
    }
    context.bot = AsyncMock()
    return context

@pytest.fixture
def mock_product():
    return Product(product_id="PROD-1", name="Карп", description="Свежий", price=150.0, unit="кг", is_available=True)
    
@pytest.fixture
def mock_product_2():
    return Product(product_id="PROD-2", name="Форель", description="Радужная", price=250.0, unit="кг", is_available=True)


# FIX: Change the patch target to where notify_admins is imported and used in client.py
@patch('app.flows.client.notify_admins') # <--- CRITICAL CHANGE HERE
@patch('app.bot.middleware.get_user_by_id')
@patch('app.flows.client.references')
@patch('app.flows.client.logs')
async def test_client_order_full_flow(mock_logs, mock_references, mock_get_user, mock_notify_admins, mock_update, mock_context, mock_product):
    """Тест полного сценария оформления заказа клиентом."""
    mock_get_user.return_value = mock_context.user_data['current_user']
    mock_references.get_available_products.return_value = [mock_product]

    # --- Шаг 1: /order -> order_start
    mock_update.callback_query = None
    next_state = await order_start(mock_update, mock_context)
    assert next_state == OrderState.SELECT_PRODUCT
    
    mock_update.message.reply_text.assert_called_once()
    call_args, call_kwargs = mock_update.message.reply_text.call_args
    assert call_args[0] == "Выберите товар для добавления в корзину:"
    assert isinstance(call_kwargs['reply_markup'], InlineKeyboardMarkup)
    assert len(call_kwargs['reply_markup'].inline_keyboard[0]) == 1

    mock_update.callback_query = AsyncMock()
    
    # --- Шаг 2: Выбор товара -> product_selected_for_order
    mock_references.get_available_products.return_value = [mock_product] 
    mock_update.callback_query.data = "prod_PROD-1"
    next_state = await product_selected_for_order(mock_update, mock_context)
    assert next_state == OrderState.ENTER_QUANTITY
    assert mock_context.user_data['selected_product'].model_dump() == mock_product.model_dump()
    mock_update.callback_query.edit_message_text.assert_called_with(f"Выбран товар: {mock_product.name}.\n\nВведите желаемое количество (в {mock_product.unit}):")

    # --- Шаг 3: Ввод количества -> quantity_received
    mock_update.message.text = "2.5"
    next_state = await quantity_received(mock_update, mock_context)
    call_args, call_kwargs = mock_update.message.reply_text.call_args
    assert call_args[0] == f"✅ {mock_product.name} (2.5 {mock_product.unit}) добавлен в корзину."
    assert isinstance(call_kwargs['reply_markup'], InlineKeyboardMarkup)
    
    # --- Шаг 4: Нажатие "Оформить заказ" -> show_cart_and_confirm
    mock_update.callback_query.data = "checkout"
    next_state = await show_cart_and_confirm(mock_update, mock_context)
    assert next_state == OrderState.CHECKOUT_OR_ADD
    call_args, call_kwargs = mock_update.callback_query.edit_message_text.call_args
    assert "Ваш заказ" in call_args[0]
    assert isinstance(call_kwargs['reply_markup'], InlineKeyboardMarkup)
    assert mock_context.user_data['total_amount'] == 150.0 * 2.5

    # --- Шаг 5: Подтверждение -> finalize_order
    mock_update.callback_query.data = "confirm_order"
    final_state = await finalize_order(mock_update, mock_context)
    assert final_state == ConversationHandler.END

    mock_logs.append_sales_order.assert_called_once()
    mock_logs.append_sales_order_item.assert_called_once()
    
    order_row: SalesOrderRow = mock_logs.append_sales_order.call_args[0][0]
    assert order_row.client_id == 789
    assert order_row.total_amount == 375.0

    # Assert that notify_admins was called once, not context.bot.send_message
    mock_notify_admins.assert_called_once()
    notify_args, notify_kwargs = mock_notify_admins.call_args
    assert notify_args[0] == mock_context # First argument is context
    assert "Новый заказ" in notify_args[1] # Second argument is the admin_message string
    assert notify_kwargs['parse_mode'] == 'HTML' # Keyword argument parse_mode

    assert 'cart' not in mock_context.user_data


@patch('app.bot.middleware.get_user_by_id')
@patch('app.flows.client.references')
async def test_client_order_add_more_flow(mock_references, mock_get_user, mock_update, mock_context, mock_product, mock_product_2):
    """Тест: сценарий с добавлением второго товара в корзину."""
    mock_get_user.return_value = mock_context.user_data['current_user']

    # Arrange
    mock_references.get_available_products.return_value = [mock_product, mock_product_2]
    mock_context.user_data['selected_product'] = mock_product
    mock_context.user_data['cart'] = {}

    # --- Шаг 1: Добавляем первый товар
    mock_update.message.text = "1.0"
    await quantity_received(mock_update, mock_context)
    assert 'PROD-1' in mock_context.user_data['cart']

    # --- Шаг 2: Нажимаем "Добавить еще товар"
    mock_update.callback_query.data = "add_more"
    mock_update.message = None # Simulate callback query, so message is None
    next_state = await order_start(mock_update, mock_context)
    assert next_state == OrderState.SELECT_PRODUCT

    mock_update.callback_query.edit_message_text.assert_called_once()
    call_args, call_kwargs = mock_update.callback_query.edit_message_text.call_args
    assert call_args[0] == "Выберите товар для добавления в корзину:"
    assert isinstance(call_kwargs['reply_markup'], InlineKeyboardMarkup)
    assert len(call_kwargs['reply_markup'].inline_keyboard[0]) == 2

    mock_update.message = AsyncMock() # Restore mock_update.message for the next step

    # --- Шаг 3: Добавляем второй товар
    mock_update.callback_query.edit_message_text.reset_mock() 
    mock_update.callback_query.data = "prod_PROD-2"
    await product_selected_for_order(mock_update, mock_context)
    mock_update.message.text = "0.5"
    await quantity_received(mock_update, mock_context)

    # Assert: Проверяем, что в корзине два товара
    assert 'PROD-1' in mock_context.user_data['cart']
    assert 'PROD-2' in mock_context.user_data['cart']
    assert mock_context.user_data['cart']['PROD-2']['quantity'] == 0.5

async def test_client_order_invalid_quantity(mock_update, mock_context, mock_product):
    """Тест: обработка неверного ввода количества."""
    mock_context.user_data['selected_product'] = mock_product
    
    mock_update.message.text = "abc"
    next_state = await quantity_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите положительное число (например, 1.5 или 10).")
    assert next_state == OrderState.ENTER_QUANTITY

    mock_update.message.text = "-5"
    next_state = await quantity_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите положительное число (например, 1.5 или 10).")
    assert next_state == OrderState.ENTER_QUANTITY

@patch('app.flows.client.cancel', new_callable=AsyncMock)
async def test_client_order_cancel_flow(mock_cancel, mock_update, mock_context):
    """Тест: отмена заказа на шаге подтверждения."""
    mock_cancel.return_value = ConversationHandler.END
    mock_context.user_data['cart'] = {'PROD-1': {}}

    mock_update.callback_query.data = "cancel_order"
    final_state = await mock_cancel(mock_update, mock_context)

    mock_cancel.assert_called_once_with(mock_update, mock_context)
    assert final_state == ConversationHandler.END