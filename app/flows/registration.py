from enum import Enum, auto
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from app.bot.notifications import notify_admins
from app.models.user import User, UserRole
from app.sheets import logs, references
from app.utils.logger import log
from .common import cancel


class RegistrationState(Enum):
    """Состояния для диалога регистрации."""
    NAME = auto()
    PHONE = auto()
    CONFIRM = auto()


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> RegistrationState | int:
    """
    Начинает диалог регистрации. Проверяет, не зарегистрирован ли пользователь уже.
    """
    user_id = update.effective_user.id
    if references.get_user_by_id(user_id):
        await update.message.reply_text("Вы уже зарегистрированы в системе.")
        return ConversationHandler.END

    await update.message.reply_text("Начинаем регистрацию. Пожалуйста, введите ваше Имя и Фамилию:")
    return RegistrationState.NAME


async def name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> RegistrationState:
    """
    Принимает имя пользователя и запрашивает номер телефона.
    """
    context.user_data['name'] = update.message.text

    phone_button = KeyboardButton(text="📱 Отправить мой номер телефона", request_contact=True)
    reply_markup = ReplyKeyboardMarkup([[phone_button]], one_time_keyboard=True, resize_keyboard=True)

    # --- ИЗМЕНЕНИЕ 1: Обновлен текст ---
    await update.message.reply_text(
        "Отлично! Теперь для верификации, пожалуйста, отправьте ваш номер телефона, нажав на кнопку ниже.",
        reply_markup=reply_markup
    )
    return RegistrationState.PHONE


# --- ИЗМЕНЕНИЕ 2: Функция переименована и теперь обрабатывает ТОЛЬКО контакты ---
async def contact_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> RegistrationState:
    """
    Принимает контакт, проверяет, что он принадлежит пользователю, и ожидает подтверждения.
    """
    contact = update.message.contact
    
    # Главная проверка безопасности
    if contact.user_id != update.effective_user.id:
        await update.message.reply_text(
            "❗️Это не ваш контакт. Пожалуйста, поделитесь своим собственным контактом для завершения регистрации.",
            reply_markup=update.message.reply_markup # Снова показываем ту же кнопку
        )
        return RegistrationState.PHONE

    phone_number = contact.phone_number
    context.user_data['phone'] = phone_number
    user_name = context.user_data['name']

    await update.message.reply_text(
        f"Спасибо! Проверьте данные:\n\n"
        f"Имя: {user_name}\n"
        f"Телефон: {phone_number}\n\n"
        f"Если всё верно, отправьте /confirm для завершения регистрации.",
        reply_markup=ReplyKeyboardRemove()
    )
    return RegistrationState.CONFIRM

# --- ИЗМЕНЕНИЕ 3: Новая функция для обработки неверного ввода (текстом) ---
async def phone_text_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> RegistrationState:
    """
    Сообщает пользователю, что ручной ввод номера не допускается.
    """
    await update.message.reply_text(
        "Пожалуйста, используйте кнопку '📱 Отправить мой номер телефона' для подтверждения вашего номера. Ввод вручную не допускается."
    )
    return RegistrationState.PHONE


async def confirm_registration(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Завершает регистрацию: сохраняет данные, уведомляет пользователя и всех администраторов.
    """
    try:
        user_model = User(
            user_id=update.effective_user.id,
            user_name=context.user_data['name'],
            phone_number=context.user_data['phone'],
            role=UserRole.PENDING
        )
        logs.append_new_user(user_model)
        references.get_all_users.cache_clear()

        await update.message.reply_text(
            "✅ Ваша заявка принята! Администратор рассмотрит её в ближайшее время. Вы получите уведомление."
        )

        admin_message = (
            f"🔔 Новый пользователь зарегистрировался!\n\n"
            f"ID: {user_model.id}\n"
            f"Имя: {user_model.name}\n"
            f"Телефон: {user_model.phone}\n\n"
            f"Назначьте роль через панель администратора."
        )
        
        # --- ИЗМЕНЕНИЕ 2: Заменяем старый вызов на новый ---
        await notify_admins(context, admin_message)
        # --- КОНЕЦ ИЗМЕНЕНИЯ ---

    except Exception as e:
        log.error(f"Ошибка при подтверждении регистрации для user_id {update.effective_user.id}: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении заявки. Пожалуйста, попробуйте позже.")
    finally:
        context.user_data.clear()

    return ConversationHandler.END


# Определяем обработчик диалога регистрации
registration_conv_handler = ConversationHandler(
    entry_points=[CommandHandler("register", register_start)],
    states={
        RegistrationState.NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, name_received)],
        # --- ИЗМЕНЕНИЕ 4: Обновлена логика обработки состояния PHONE ---
        RegistrationState.PHONE: [
            MessageHandler(filters.CONTACT, contact_received),
            MessageHandler(filters.TEXT & ~filters.COMMAND, phone_text_received)
        ],
        RegistrationState.CONFIRM: [CommandHandler("confirm", confirm_registration)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)