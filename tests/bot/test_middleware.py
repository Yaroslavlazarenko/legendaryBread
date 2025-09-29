# tests/bot/test_middleware.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.bot.middleware import restricted
from app.models.user import User, UserRole

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

@pytest.fixture
def mock_decorated_func():
    return AsyncMock()

async def test_restricted_allowed_user(mock_update, mock_context, mock_decorated_func):
    """Тест: Пользователь с разрешенной ролью получает доступ."""
    user = User(user_id=123, user_name="Admin", role=UserRole.ADMIN)
    
    with patch('app.bot.middleware.get_user_by_id', return_value=user):
        decorator = restricted(allowed_roles=[UserRole.ADMIN, UserRole.OPERATOR])
        wrapped_func = decorator(mock_decorated_func)
        await wrapped_func(mock_update, mock_context)

    mock_decorated_func.assert_called_once_with(mock_update, mock_context)
    assert mock_context.user_data['current_user'] == user

async def test_restricted_disallowed_user(mock_update, mock_context, mock_decorated_func):
    """Тест: Пользователь с запрещенной ролью не получает доступ."""
    user = User(user_id=123, user_name="Client", role=UserRole.CLIENT)

    with patch('app.bot.middleware.get_user_by_id', return_value=user):
        decorator = restricted(allowed_roles=[UserRole.ADMIN])
        wrapped_func = decorator(mock_decorated_func)
        await wrapped_func(mock_update, mock_context)
    
    mock_decorated_func.assert_not_called()
    mock_update.message.reply_text.assert_called_with("⛔️ У вас нет доступа к этой команде.")

async def test_restricted_unregistered_user_no_self_register(mock_update, mock_context, mock_decorated_func):
    """Тест: Незарегистрированный пользователь получает отказ (self_register=False)."""
    with patch('app.bot.middleware.get_user_by_id', return_value=None):
        decorator = restricted(allowed_roles=[UserRole.ADMIN], self_register=False)
        wrapped_func = decorator(mock_decorated_func)
        await wrapped_func(mock_update, mock_context)

    mock_decorated_func.assert_not_called()
    mock_update.message.reply_text.assert_called_with("Вы не зарегистрированы в системе. Обратитесь к администратору.")

async def test_restricted_unregistered_user_with_self_register(mock_update, mock_context, mock_decorated_func):
    """Тест: Незарегистрированный пользователь получает предложение зарегистрироваться (self_register=True)."""
    with patch('app.bot.middleware.get_user_by_id', return_value=None):
        decorator = restricted(allowed_roles=[UserRole.ADMIN], self_register=True)
        wrapped_func = decorator(mock_decorated_func)
        await wrapped_func(mock_update, mock_context)

    mock_decorated_func.assert_not_called()
    mock_update.message.reply_text.assert_called_with(
        "Вы не зарегистрированы в системе. "
        "Чтобы начать, пожалуйста, пройдите регистрацию с помощью команды /register"
    )

async def test_restricted_pending_user(mock_update, mock_context, mock_decorated_func):
    """Тест: Пользователь со статусом PENDING получает сообщение об ожидании."""
    user = User(user_id=123, user_name="Pending User", role=UserRole.PENDING)

    with patch('app.bot.middleware.get_user_by_id', return_value=user):
        decorator = restricted(allowed_roles=[UserRole.CLIENT])
        wrapped_func = decorator(mock_decorated_func)
        await wrapped_func(mock_update, mock_context)

    mock_decorated_func.assert_not_called()
    mock_update.message.reply_text.assert_called_with("Ваша заявка на регистрацию ожидает подтверждения администратором.")