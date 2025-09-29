import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.ext import ConversationHandler
from app.flows.manage_products import (
    ProductState, add_product_start, add_name_received, add_desc_received, add_price_received, 
    add_unit_received, save_new_product, products_start, select_product,
    toggle_product_status, edit_product_start, ask_for_new_value, save_edited_value,
    back_to_product_list
)
from app.models.product import Product

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

# --- NO CHANGES TO THESE TESTS ---
async def test_add_product_invalid_price(mock_update, mock_context):
    """Тест: ввод некорректной цены (текст) при добавлении товара."""
    mock_context.user_data['new_product'] = {'name': 'Рыба', 'description': 'Свежая'}
    mock_update.message.text = "очень дорого"
    next_state = await add_price_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите положительное число.")
    assert next_state == ProductState.ADD_PRICE

async def test_add_product_negative_price(mock_update, mock_context):
    """Тест: ввод отрицательной цены при добавлении товара."""
    mock_context.user_data['new_product'] = {'name': 'Рыба', 'description': 'Свежая'}
    mock_update.message.text = "-150"
    next_state = await add_price_received(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Введите положительное число.")
    assert next_state == ProductState.ADD_PRICE

@patch('app.flows.manage_products.products_start', new_callable=AsyncMock)
async def test_back_to_list_from_product_actions(mock_products_start, mock_update, mock_context):
    """Тест: нажатие кнопки "Назад к списку" из меню действий над товаром."""
    # Arrange: Устанавливаем начальное состояние
    mock_context.user_data['selected_product_id'] = 'PROD-123'
    # Настраиваем мок, чтобы он возвращал конечное состояние, как настоящая функция
    mock_products_start.return_value = ProductState.MENU

    # Act: Вызываем наш обработчик
    next_state = await back_to_product_list(mock_update, mock_context)

    # Assert:
    # 1. Проверяем, что состояние было очищено ДО вызова products_start
    assert 'selected_product_id' not in mock_context.user_data
    
    # 2. Проверяем, что products_start была вызвана ровно один раз
    mock_products_start.assert_called_once_with(mock_update, mock_context)
    
    # 3. Проверяем, что было возвращено правильное конечное состояние
    assert next_state == ProductState.MENU

@patch('app.flows.manage_products.logs.append_product')
@patch('app.flows.manage_products.references.get_all_products')
async def test_add_product_happy_path(mock_get_all, mock_append, mock_update, mock_context):
    """Тест 'happy path' для добавления нового товара."""
    mock_update.callback_query.data = "add_new"
    await add_product_start(mock_update, mock_context)
    mock_update.message.text = "Супер Карп"
    await add_name_received(mock_update, mock_context)
    mock_update.message.text = "Очень большой"
    await add_desc_received(mock_update, mock_context)
    mock_update.message.text = "250.5"
    await add_price_received(mock_update, mock_context)
    mock_update.message.text = "кг"
    await add_unit_received(mock_update, mock_context)
    mock_update.callback_query.data = "save_new"
    mock_get_all.return_value = [] 
    
    await save_new_product(mock_update, mock_context)
    
    mock_append.assert_called_once()
    saved_product: Product = mock_append.call_args[0][0]
    assert saved_product.name == "Супер Карп"
    assert saved_product.price == 250.5


# --- CORRECTED TESTS ---

@patch('app.flows.manage_products.products_start', new_callable=AsyncMock)
@patch('app.flows.manage_products.references')
async def test_toggle_product_status_flow(mock_references, mock_products_start, mock_update, mock_context):
    """Тест сценария смены статуса доступности товара."""
    prod_id = "PROD-TOGGLE"
    # CORRECTED: Use 'product_id' instead of 'id'
    mock_product = Product(product_id=prod_id, name="Тест", is_available=True, description="", price=1, unit="")
    mock_context.user_data['selected_product_id'] = prod_id
    mock_references.get_product_by_id.return_value = mock_product
    mock_references.update_product_status.return_value = True

    mock_update.callback_query.data = "toggle_status"
    await toggle_product_status(mock_update, mock_context)
    
    mock_references.update_product_status.assert_called_once_with(prod_id, False)
    mock_update.callback_query.edit_message_text.assert_called_with("✅ Статус товара успешно изменен.")
    mock_products_start.assert_called_once_with(mock_update, mock_context)
    
@patch('app.flows.manage_products.references')
async def test_edit_product_flow_price(mock_references, mock_update, mock_context):
    """Тест полного сценария редактирования цены товара."""
    prod_id = "PROD-EDIT"
    mock_product = Product(product_id=prod_id, name="Товар", description="...", price=100, unit="кг", is_available=True)
    mock_references.get_product_by_id.return_value = mock_product
    mock_references.update_product_details.return_value = True
    
    # Steps 1-3: User clicks through menus
    mock_update.callback_query.data = f"select_{prod_id}"
    await select_product(mock_update, mock_context)
    mock_update.callback_query.data = "edit_data"
    await edit_product_start(mock_update, mock_context)
    mock_update.callback_query.data = "edit_price"
    await ask_for_new_value(mock_update, mock_context)
    
    # --- CORRECTED SIMULATION ---
    # Step 4: User sends a message. An update from a message has no callback_query.
    # We must reset this on the mock to simulate the correct update type.
    mock_update.callback_query = None
    mock_update.message.text = "125.50"
    
    # Set the return value for the get_product_by_id call inside _display_product_actions
    mock_product_after_edit = Product(product_id=prod_id, name="Товар", description="...", price=125.50, unit="кг", is_available=True)
    mock_references.get_product_by_id.return_value = mock_product_after_edit
    
    next_state = await save_edited_value(mock_update, mock_context)
    
    # --- CORRECTED ASSERTIONS ---
    mock_references.update_product_details.assert_called_once_with(prod_id, 'price', 125.50)
    
    # Check that reply_text was called twice: once with confirmation, once with the updated product card.
    assert mock_update.message.reply_text.call_count == 2
    
    # Check the first call's content
    first_call_args = mock_update.message.reply_text.call_args_list[0].args
    assert first_call_args[0] == "✅ Поле 'price' успешно обновлено."
    
    # Check the second (last) call's content
    second_call_args = mock_update.message.reply_text.call_args_list[1].args
    assert "<b>Цена:</b> 125.50 грн / кг" in second_call_args[0]
    
    assert next_state == ProductState.SELECT_ACTION

@patch('app.flows.manage_products.references')
async def test_edit_product_invalid_price(mock_references, mock_update, mock_context):
    """Тест: ввод неверной цены при редактировании."""
    prod_id = "PROD-EDIT"
    mock_context.user_data['selected_product_id'] = prod_id
    mock_context.user_data['edit_field'] = 'price'

    mock_update.message.text = "дорого"
    next_state = await save_edited_value(mock_update, mock_context)

    mock_references.update_product_details.assert_not_called()
    mock_update.message.reply_text.assert_called_with("❗️Неверный формат. Цена должна быть числом. Попробуйте снова.")
    assert next_state == ProductState.EDIT_FIELD_VALUE
    assert 'edit_field' in mock_context.user_data