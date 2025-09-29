import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY

from telegram import Update
from telegram.ext import ConversationHandler

from app.flows.registration import (
    RegistrationState, register_start, name_received, contact_received, phone_text_received, confirm_registration # ИЗМЕНЕНО: Импорт phone_received заменен на contact_received и phone_text_received
)
from app.models.user import User, UserRole

pytestmark = pytest.mark.asyncio

@pytest.fixture
def mock_update():
    update = MagicMock(spec=Update)
    update.effective_user.id = 123
    update.message = AsyncMock()
    update.message.contact = None # По умолчанию контакт не отправлен
    update.callback_query = None # Добавим, на случай если где-то используется
    return update

@pytest.fixture
def mock_context():
    context = MagicMock()
    context.user_data = {}
    context.bot = AsyncMock()
    return context

@patch('app.flows.registration.references')
@patch('app.flows.registration.logs')
@patch('app.flows.registration.notify_admins', new_callable=AsyncMock) # Мокаем notify_admins
async def test_registration_full_flow_with_contact_button_success(
    mock_notify_admins, mock_logs, mock_references, mock_update, mock_context
):
    """Тест полного сценария регистрации, когда телефон отправлен через кнопку."""
    
    mock_references.get_user_by_id.return_value = None

    # 1. register_start
    next_state = await register_start(mock_update, mock_context)
    mock_update.message.reply_text.assert_called_with("Начинаем регистрацию. Пожалуйста, введите ваше Имя и Фамилию:")
    assert next_state == RegistrationState.NAME

    # 2. name_received
    mock_update.message.text = "Тестовый Пользователь"
    next_state = await name_received(mock_update, mock_context)
    assert mock_context.user_data['name'] == "Тестовый Пользователь"
    mock_update.message.reply_text.assert_called_with(
        "Отлично! Теперь для верификации, пожалуйста, отправьте ваш номер телефона, нажав на кнопку ниже.", # ИЗМЕНЕНО: текст сообщения
        reply_markup=ANY
    )
    assert next_state == RegistrationState.PHONE

    # 3. contact_received (имитация отправки контакта через кнопку)
    contact_phone = "+380991234567"
    mock_update.message.contact = MagicMock()
    mock_update.message.contact.phone_number = contact_phone
    mock_update.message.contact.user_id = mock_update.effective_user.id # Важно, что контакт от самого пользователя
    mock_update.message.text = None # Важно: если отправлен контакт, то message.text должен быть None
    
    next_state = await contact_received(mock_update, mock_context) # ИЗМЕНЕНО: вызываем contact_received
    assert mock_context.user_data['phone'] == contact_phone
    assert "Проверьте данные" in mock_update.message.reply_text.call_args[0][0]
    assert "Телефон: +380991234567" in mock_update.message.reply_text.call_args[0][0]
    assert next_state == RegistrationState.CONFIRM

    # 4. confirm_registration
    mock_update.message.text = "/confirm" # Имитируем команду /confirm
    mock_update.message.reply_markup = None # Убираем reply_markup после confirm_registration
    final_state = await confirm_registration(mock_update, mock_context)
    
    mock_logs.append_new_user.assert_called_once()
    saved_user: User = mock_logs.append_new_user.call_args[0][0]
    assert saved_user.id == 123
    assert saved_user.name == "Тестовый Пользователь"
    assert saved_user.phone == "+380991234567" # Проверяем сохраненный телефон
    assert saved_user.role == UserRole.PENDING

    mock_update.message.reply_text.assert_called_with(
        "✅ Ваша заявка принята! Администратор рассмотрит её в ближайшее время. Вы получите уведомление."
    )
    mock_notify_admins.assert_called_once_with(ANY, ANY) # Проверяем вызов notify_admins

    assert final_state == ConversationHandler.END
    assert not mock_context.user_data # user_data должны быть очищены


@patch('app.flows.registration.references')
async def test_register_start_already_registered_user(mock_references, mock_update, mock_context):
    """Тест: пользователь пытается зарегистрироваться, но он уже есть в системе."""
    mock_references.get_user_by_id.return_value = User(user_id=123, user_name="Existing User", role=UserRole.CLIENT)

    final_state = await register_start(mock_update, mock_context)
    
    mock_references.get_user_by_id.assert_called_once_with(123)
    mock_update.message.reply_text.assert_called_with("Вы уже зарегистрированы в системе.")
    assert final_state == ConversationHandler.END


@patch('app.flows.registration.references')
async def test_phone_text_received_when_manual_input_not_allowed(mock_references, mock_update, mock_context):
    """Тест: пользователь пытается ввести телефон текстом, когда это не разрешено."""
    mock_references.get_user_by_id.return_value = None
    mock_context.user_data['name'] = "Тестовый Пользователь" # Имитируем, что имя уже введено

    mock_update.message.text = "+380501234567" # Пользователь вводит телефон текстом
    mock_update.message.contact = None # Контакт не отправлен

    next_state = await phone_text_received(mock_update, mock_context) # ИЗМЕНЕНО: вызываем phone_text_received

    mock_update.message.reply_text.assert_called_with(
        "Пожалуйста, используйте кнопку '📱 Отправить мой номер телефона' для подтверждения вашего номера. Ввод вручную не допускается."
    )
    assert next_state == RegistrationState.PHONE # Состояние не меняется, ждем правильного ввода


@patch('app.flows.registration.references')
async def test_contact_received_with_wrong_user_id(mock_references, mock_update, mock_context):
    """Тест: пользователь отправляет контакт, но он принадлежит другому user_id."""
    mock_references.get_user_by_id.return_value = None
    mock_context.user_data['name'] = "Тестовый Пользователь"
    
    contact_phone = "+1234567890"
    mock_update.message.contact = MagicMock()
    mock_update.message.contact.phone_number = contact_phone
    mock_update.message.contact.user_id = 999 # Неправильный user_id
    mock_update.message.text = None
    
    # Чтобы mock_update.message.reply_markup был определен для повторного показа кнопки
    mock_update.message.reply_markup = MagicMock() 

    next_state = await contact_received(mock_update, mock_context)

    mock_update.message.reply_text.assert_called_with(
        "❗️Это не ваш контакт. Пожалуйста, поделитесь своим собственным контактом для завершения регистрации.",
        reply_markup=mock_update.message.reply_markup
    )
    assert next_state == RegistrationState.PHONE
    assert 'phone' not in mock_context.user_data # Телефон не должен быть сохранен