# flows/common.py

"""
Общие вспомогательные функции, используемые в различных сценариях (flows).
"""

from __future__ import annotations # Позволяет использовать User в аннотациях без кавычек

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler

from app.models.user import User # <-- ДОБАВЛЕН ИМПОРТ
from app.sheets import references


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Универсальный обработчик для отмены любого диалога ConversationHandler.

    Завершает диалог, уведомляет пользователя и очищает временные данные
    из `context.user_data`, но сохраняет ключ 'current_user' для поддержания
    сессии пользователя.
    """
    message_text = "Действие отменено."
    
    if update.callback_query:
        # Если команда пришла от кнопки, редактируем исходное сообщение
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text)
    else:
        # Если пользователь ввел /cancel, отправляем новое сообщение
        await update.message.reply_text(message_text)
        
    # "Безопасная" очистка user_data для сохранения сессии
    user_backup: User | None = context.user_data.get('current_user')
    context.user_data.clear()
    if user_backup:
        context.user_data['current_user'] = user_backup
        
    return ConversationHandler.END


async def ask_for_pond_selection(update: Update, text: str) -> bool:
    """
    Отправляет пользователю сообщение с кнопками для выбора активного водоёма.

    Args:
        update: Объект Update от Telegram.
        text: Текст, который будет показан пользователю над кнопками выбора.

    Returns:
        bool: True, если сообщение с выбором было успешно отправлено.
              False, если нет активных водоёмов и отправлено сообщение об ошибке.
    """
    # Получаем только активные водоёмы, доступные для операций
    ponds = references.get_active_ponds()
    
    # Обрабатываем случай, когда водоёмов нет
    if not ponds:
        await update.message.reply_text(
            "В системе нет активных водоёмов. Обратитесь к администратору, чтобы добавить или активировать их."
        )
        return False

    # Создаем клавиатуру с кнопками, где каждая кнопка - это один водоём
    keyboard = [
        [InlineKeyboardButton(p.name, callback_data=f"pond_{p.id}")] 
        for p in ponds
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение с запросом
    await update.message.reply_text(text, reply_markup=reply_markup)
    return True

async def handle_expired_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обрабатывает нажатия на inline-кнопки, которые "устарели" после перезапуска бота.
    """
    query = update.callback_query
    # Отвечаем на колбэк, чтобы убрать "часики" на кнопке.
    # show_alert=True покажет пользователю всплывающее уведомление.
    await query.answer(
        text="⚠️ Бот был перезапущен. Пожалуйста, начните действие заново из главного меню.",
        show_alert=True
    )
    
    # Опционально: можно отредактировать сообщение со старой клавиатурой, чтобы убрать кнопки.
    try:
        await query.edit_message_text(
            text=query.message.text + "\n\n(Это меню больше неактивно)",
            reply_markup=None
        )
    except Exception:
        # Может возникнуть ошибка, если сообщение слишком старое, игнорируем ее.
        pass