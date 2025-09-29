import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

# Import ReplyKeyboardMarkup for asserting the type of the mock's return value
from telegram import ReplyKeyboardMarkup 
from app.bot.handlers import start
from app.flows.client import catalog_start
from app.models.user import User, UserRole
from app.models.product import Product

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_update():
    update = MagicMock()
    update.effective_user.id = 123
    update.message = AsyncMock()
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    return context

# FIX: Patch the create_main_menu_keyboard function from where it's used in app.bot.handlers
# Also, adjust the parametrize data and the assertions to match the actual message content.
@patch('app.bot.handlers.create_main_menu_keyboard', return_value=MagicMock(spec=ReplyKeyboardMarkup))
@patch('app.bot.middleware.get_user_by_id')
@pytest.mark.parametrize("user_role, expected_admin_notification_text", [
    (UserRole.ADMIN, "Для настройки уведомлений используйте /notifications"),
    (UserRole.OPERATOR, None), # No specific additional text for operator in greeting
    (UserRole.CLIENT, None),    # No specific additional text for client in greeting
])
async def test_start_command_for_different_roles(mock_get_user, mock_create_keyboard, user_role, expected_admin_notification_text, mock_update, mock_context):
    """Тест: команда /start показывает правильное меню для каждой роли."""
    # Arrange
    user = User(user_id=123, user_name="Test", role=user_role)
    mock_get_user.return_value = user

    # Act
    await start(mock_update, mock_context)

    # Assert
    mock_update.message.reply_text.assert_called_once()
    
    # Extract arguments from the call
    called_text = mock_update.message.reply_text.call_args[0][0]
    called_markup = mock_update.message.reply_text.call_args[1]['reply_markup']

    # Assert core greeting components
    assert f"Привет, {user.name}!" in called_text
    assert f"Ваша роль: {user.role.value}." in called_text # Ensure the role is mentioned
    assert "Используйте кнопки ниже для навигации." in called_text

    # Assert role-specific text (only for admin in this case)
    if expected_admin_notification_text:
        assert expected_admin_notification_text in called_text
    else:
        assert "Для настройки уведомлений" not in called_text # Ensure admin-specific text is NOT present for others

    # Assert that the main menu keyboard was created with the correct role
    mock_create_keyboard.assert_called_once_with(user_role)
    # Assert that the reply_text used the keyboard returned by our mock
    assert called_markup == mock_create_keyboard.return_value

    # Ensure current_user is stored in context
    assert mock_context.user_data['current_user'] == user

# The existing tests for catalog_start are generally correct, assuming `catalog_start`
# behaves as described (two reply_text calls). No changes are needed there.

@patch('app.flows.client.references.get_available_products')
@patch('app.bot.middleware.get_user_by_id')
async def test_catalog_start_with_products(mock_get_user, mock_get_products, mock_update, mock_context):
    """Тест: /catalog показывает товары, если они есть."""
    # Arrange
    client_user = User(user_id=123, user_name="Client", role=UserRole.CLIENT)
    mock_get_user.return_value = client_user
    mock_get_products.return_value = [
        Product(product_id='p1', name='Карп', description='Свежий', price=150, unit='кг', is_available=True)
    ]

    # Act
    await catalog_start(mock_update, mock_context)

    # Assert
    # Check that exactly two calls were made.
    assert mock_update.message.reply_text.call_count == 2

    # Check the content of the FIRST call for the catalog details.
    first_call_text = mock_update.message.reply_text.call_args_list[0].args[0]
    assert "Наш Каталог" in first_call_text
    assert "Карп" in first_call_text

    # Check the content of the LAST call for the "how to order" message.
    # `assert_called_with` conveniently checks the most recent call.
    mock_update.message.reply_text.assert_called_with(
        'Для оформления заказа используйте команду /order'
    )
    
@patch('app.flows.client.references.get_available_products')
@patch('app.bot.middleware.get_user_by_id')
async def test_catalog_start_no_products(mock_get_user, mock_get_products, mock_update, mock_context):
    """Тест: /catalog сообщает об отсутствии товаров."""
    # Arrange
    client_user = User(user_id=123, user_name="Client", role=UserRole.CLIENT)
    
    # Mock for the decorator
    mock_get_user.return_value = client_user
    
    # Mock for the function body
    mock_get_products.return_value = []

    # Act
    await catalog_start(mock_update, mock_context)

    # Assert
    mock_update.message.reply_text.assert_called_once_with("Извините, в данный момент доступных товаров нет.")