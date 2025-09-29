# flows/manage_feed_types.py
from app.bot.keyboards import ReplyButton
import uuid
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)
from app.bot.middleware import restricted
from app.models.user import UserRole
from app.models.feeding import FeedType
from app.sheets import references, logs
from app.bot.keyboards import create_paginated_keyboard
from .common import cancel

# --- ИЗМЕНЕНИЕ: Состояния диалога заменены на Enum для надежности ---
class FeedState(Enum):
    MENU = auto()
    SELECT_ACTION = auto()
    ADD_NAME = auto()
    CONFIRM_ADD = auto()
    EDIT_NAME = auto()

# --- Вспомогательная функция для отображения меню действий ---
async def _display_feed_type_actions(feed_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """
    Отображает детали типа корма и меню действий (редактировать, изменить статус).
    Используется как точка возврата после различных действий.
    """
    feed_type = references.get_feed_type_by_id(feed_id)
    if not feed_type:
        text = "Тип корма не найден или был удален. Возврат в главное меню."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        # Безопасный возврат в начальное состояние
        return await feed_types_start(update, context, clear_selection=True)

    context.user_data['selected_feed_type_id'] = feed_id
    status_text = "Активен" if feed_type.is_active else "Не активен"
    toggle_text = "Сделать неактивным" if feed_type.is_active else "Сделать активным"
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 {toggle_text}", callback_data="toggle_status")],
        [InlineKeyboardButton("📝 Редактировать название", callback_data="edit_name")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="back_to_list")]
    ]
    
    text = f"<b>Тип корма:</b> {feed_type.name}\n<b>Статус:</b> {status_text}"
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Универсальный способ ответить: редактировать, если можно, или отправить новое сообщение
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')
        
    return FeedState.SELECT_ACTION

# --- Основные обработчики диалога ---

@restricted(allowed_roles=[UserRole.ADMIN])
async def feed_types_start(update: Update, context: ContextTypes.DEFAULT_TYPE, clear_selection: bool = False) -> FeedState:
    """Отображает главный список типов кормов с пагинацией."""
    query = update.callback_query
    page = 0

    if clear_selection and 'selected_feed_type_id' in context.user_data:
        del context.user_data['selected_feed_type_id']

    if query:
        await query.answer()
        if query.data.startswith("feed_types_page_"):
            page = int(query.data.split("_")[3])
        # Обработка кнопки "Назад к списку"
        elif query.data == "back_to_list" and 'selected_feed_type_id' in context.user_data:
             del context.user_data['selected_feed_type_id']


    feed_types = references.get_feed_types()
    extra_buttons = [[InlineKeyboardButton("➕ Добавить новый тип", callback_data="add_new")]]
    
    reply_markup = create_paginated_keyboard(
        items=feed_types, page=page, page_size=5,
        button_text_formatter=lambda ft: f"{'✅' if ft.is_active else '☑️'} {ft.name}",
        button_callback_formatter=lambda ft: f"select_{ft.id}",
        pagination_callback_prefix="feed_types_page_",
        extra_buttons=extra_buttons
    )
    
    text = "Управление типами кормов:"
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    return FeedState.MENU

async def select_feed_type_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Обрабатывает выбор типа корма из списка."""
    query = update.callback_query
    await query.answer()
    feed_id = query.data.split("_")[1]
    return await _display_feed_type_actions(feed_id, update, context)

async def toggle_feed_type_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Переключает статус активности типа корма."""
    query = update.callback_query
    await query.answer()
    feed_id = context.user_data['selected_feed_type_id']
    
    feed_type = references.get_feed_type_by_id(feed_id)
    if not feed_type:
        await query.edit_message_text("❌ Ошибка: тип корма не найден.")
        return await feed_types_start(update, context, clear_selection=True)

    success = references.update_feed_type_status(feed_id, not feed_type.is_active)
    if success:
        await query.edit_message_text("✅ Статус успешно изменен.")
    else:
        await query.edit_message_text("❌ Произошла ошибка при изменении статуса.")
        
    # Возвращаемся в главное меню, чтобы список обновился
    return await feed_types_start(update, context)

async def ask_for_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Запрашивает новое название для типа корма."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Введите новое название типа корма:")
    return FeedState.EDIT_NAME

async def save_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Сохраняет новое название и возвращает в меню действий."""
    new_name = update.message.text.strip()
    if not new_name:
        await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз.")
        return FeedState.EDIT_NAME

    feed_id = context.user_data['selected_feed_type_id']
    success = references.update_feed_type_details(feed_id, 'name', new_name)
    
    await update.message.reply_text("✅ Название обновлено." if success else "❌ Ошибка при обновлении.")
    
    return await _display_feed_type_actions(feed_id, update, context)

# --- Сценарий добавления нового типа корма ---
    
async def add_feed_type_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Начинает процесс добавления нового типа корма."""
    query = update.callback_query
    await query.answer()
    context.user_data['new_feed_type_data'] = {'id': f"FEED-{uuid.uuid4().hex[:6].upper()}"}
    await query.edit_message_text("Введите название нового типа корма:")
    return FeedState.ADD_NAME

async def add_feed_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Получает название и запрашивает подтверждение."""
    feed_name = update.message.text.strip()
    if not feed_name:
        await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз.")
        return FeedState.ADD_NAME
        
    context.user_data['new_feed_type_data']['name'] = feed_name
    data = context.user_data['new_feed_type_data']
    
    summary = f"<b>Подтвердите создание нового типа корма:</b>\n\n<b>Название:</b> {data['name']}\n(ID будет присвоен автоматически)"
    keyboard = [[
        InlineKeyboardButton("✅ Сохранить", callback_data="save_new"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return FeedState.CONFIRM_ADD

async def save_new_feed_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> FeedState:
    """Сохраняет новый тип корма в Google Sheets."""
    query = update.callback_query
    await query.answer()
    try:
        data = context.user_data.pop('new_feed_type_data') # Используем pop для очистки
        feed_type = FeedType(feed_id=data['id'], name=data['name'], is_active=True)
        logs.append_feed_type(feed_type)
        references.get_feed_types.cache_clear()
        await query.edit_message_text(f"✅ Тип корма '{feed_type.name}' успешно добавлен.")
    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка: {e}")
    
    return await feed_types_start(update, context)


# --- ConversationHandler ---
manage_feed_types_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.MANAGE_FEED_TYPES), feed_types_start)],
    states={
        FeedState.MENU: [
            CallbackQueryHandler(select_feed_type_for_action, pattern="^select_"),
            CallbackQueryHandler(add_feed_type_start, pattern="^add_new$"),
            CallbackQueryHandler(feed_types_start, pattern="^feed_types_page_")
        ],
        FeedState.SELECT_ACTION: [
            CallbackQueryHandler(toggle_feed_type_status, pattern="^toggle_status$"),
            CallbackQueryHandler(ask_for_new_name, pattern="^edit_name$"),
            CallbackQueryHandler(feed_types_start, pattern="^back_to_list$")
        ],
        FeedState.ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_feed_name_received)],
        FeedState.CONFIRM_ADD: [
            CallbackQueryHandler(save_new_feed_type, pattern="^save_new$"),
            CallbackQueryHandler(feed_types_start, pattern="^cancel_add$")
        ],
        FeedState.EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_name)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)