# app/flows/settings.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler

from telegram.error import BadRequest

from app.bot.middleware import restricted
from app.models.user import UserRole
from app.sheets import references
from app.utils.logger import log

from app.bot.keyboards import create_main_menu_keyboard, ReplyButton


@restricted(allowed_roles=[UserRole.ADMIN])
async def show_notification_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (код без изменений)
    user = context.user_data['current_user']
    
    status_text = "Включены 🔔" if user.notifications_enabled else "Выключены 🔕"
    button_text = "Выключить 🔕" if user.notifications_enabled else "Включить 🔔"
    callback_data = "toggle_notifications_to_off" if user.notifications_enabled else "toggle_notifications_to_on"

    inline_keyboard = [
        [InlineKeyboardButton(button_text, callback_data=callback_data)],
        [InlineKeyboardButton("⬅️ Назад в главное меню", callback_data="back_to_main_menu")]
    ]
    reply_markup_inline = InlineKeyboardMarkup(inline_keyboard)
    
    message_text = (
        f"Управление уведомлениями для администраторов.\n\n"
        f"Ваш текущий статус: <b>{status_text}</b>"
    )

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup_inline, parse_mode='HTML')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                log.info("Tried to edit message with same content (notification settings). Skipping.")
            else:
                log.error(f"Error editing message in show_notification_settings: {e}")
                await update.callback_query.answer(text="Произошла ошибка при обновлении сообщения.", show_alert=True)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup_inline, parse_mode='HTML')


@restricted(allowed_roles=[UserRole.ADMIN])
async def toggle_notification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ... (код без изменений)
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    current_user_status = context.user_data['current_user'].notifications_enabled
    
    new_status = not current_user_status
    
    success = references.update_user_notification_status(user_id, new_status)
    
    if success:
        context.user_data['current_user'].notifications_enabled = new_status
        await show_notification_settings(update, context)
    else:
        await query.edit_message_text("❌ Произошла ошибка при изменении настроек.")


async def back_to_main_menu_from_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user = context.user_data.get('current_user')
    if not user:
        await query.edit_message_text("Ошибка: не удалось определить пользователя. Пожалуйста, используйте /start.")
        return

    reply_markup_main_menu = create_main_menu_keyboard(user.role) # Это ReplyKeyboardMarkup
    
    # --- НАЧАЛО ИЗМЕНЕНИЯ: Отдельные действия для редактирования и отправки ---
    # 1. Редактируем текущее сообщение, чтобы убрать инлайн-клавиатуру
    try:
        await query.edit_message_text(
            text="Вы вернулись в главное меню.",
            reply_markup=None # <-- Убираем инлайн-клавиатуру из старого сообщения
        )
    except BadRequest as e:
        if "Message is not modified" in str(e):
            log.info("Tried to edit message with same content (back to main menu). Skipping.")
        else:
            log.error(f"Error editing message to remove inline keyboard: {e}")
            # В случае других ошибок, просто отправляем новое сообщение
            await context.bot.send_message(
                chat_id=user.id,
                text="Вы вернулись в главное меню.",
                reply_markup=reply_markup_main_menu
            )
            return

    # 2. Отправляем новое сообщение с ReplyKeyboardMarkup
    await context.bot.send_message(
        chat_id=user.id,
        text="Вот ваше главное меню:",
        reply_markup=reply_markup_main_menu
    )
    # --- КОНЕЦ ИЗМЕНЕНИЯ ---


notifications_command_handler = CommandHandler("notifications", show_notification_settings)
notifications_callback_handler = CallbackQueryHandler(toggle_notification_callback, pattern="^toggle_notifications_to_")
back_to_main_menu_handler = CallbackQueryHandler(back_to_main_menu_from_settings, pattern="^back_to_main_menu$")