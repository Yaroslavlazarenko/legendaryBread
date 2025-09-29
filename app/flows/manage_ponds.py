# flows/manage_ponds.py
from app.bot.keyboards import ReplyButton
import uuid
from datetime import date
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from app.bot.middleware import restricted
from app.bot.keyboards import create_paginated_keyboard
from app.models.user import UserRole
from app.models.pond import Pond
from app.sheets import references, logs
from .common import cancel

# --- Состояния диалога заменены на Enum ---
class PondState(Enum):
    MENU = auto()
    SELECT_ACTION = auto()
    SELECT_EDIT_FIELD = auto()
    EDIT_FIELD_VALUE = auto()
    # Состояния для добавления нового водоёма
    ADD_NAME = auto()
    ADD_TYPE = auto()
    ADD_SPECIES = auto()
    ADD_STOCKING_DATE = auto()
    ADD_INITIAL_QTY = auto()
    ADD_NOTES = auto()
    CONFIRM_ADD = auto()

# --- Вспомогательные функции ---

async def _display_pond_actions(pond_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    """Отображает детали водоёма и меню действий (редактировать, изменить статус)."""
    pond = references.get_pond_by_id(pond_id)
    if not pond:
        text = "Водоём не найден. Возможно, он был удален."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return await ponds_start(update, context, clear_selection=True)

    context.user_data['selected_pond_id'] = pond_id
    status_text = "Активен" if pond.is_active else "Не активен"
    toggle_text = "Сделать неактивным" if pond.is_active else "Сделать активным"
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 {toggle_text}", callback_data="toggle_status")],
        [InlineKeyboardButton("📝 Редактировать данные", callback_data="edit_data")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="back_to_list")]
    ]
    
    details_text = (
        f"<b>Водоём:</b> {pond.name}\n"
        f"<b>Тип:</b> {pond.type}\n"
        f"<b>Вид рыбы:</b> {pond.species or 'не указан'}\n"
        f"<b>Дата зарыбления:</b> {pond.stocking_date.isoformat() if pond.stocking_date else 'не указана'}\n"
        f"<b>Нач. кол-во:</b> {pond.initial_qty or 'не указано'}\n"
        f"<b>Заметки:</b> {pond.notes or 'нет'}\n"
        f"<b>Статус:</b> {status_text}"
    )
    
    if update.callback_query:
        await update.callback_query.edit_message_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    return PondState.SELECT_ACTION

async def _cleanup_temp_data(context: ContextTypes.DEFAULT_TYPE):
    """Безопасно очищает временные данные, сохраняя сессию."""
    user_backup = context.user_data.get('current_user')
    # Удаляем только данные, специфичные для этого диалога
    keys_to_remove = ['new_pond_data', 'selected_pond_id', 'edit_field_name']
    for key in keys_to_remove:
        if key in context.user_data:
            del context.user_data[key]


# --- Основные обработчики диалога ---

@restricted(allowed_roles=[UserRole.ADMIN])
async def ponds_start(update: Update, context: ContextTypes.DEFAULT_TYPE, clear_selection: bool = False) -> PondState:
    """Отображает главный список водоёмов с пагинацией."""
    query = update.callback_query
    page = 0

    if clear_selection and 'selected_pond_id' in context.user_data:
        del context.user_data['selected_pond_id']

    if query:
        await query.answer()
        if query.data.startswith("ponds_page_"):
            page = int(query.data.split("_")[2])
        elif query.data == "back_to_list":
             if 'selected_pond_id' in context.user_data:
                del context.user_data['selected_pond_id']

    ponds = references.get_all_ponds()
    extra_buttons = [[InlineKeyboardButton("➕ Добавить новый водоём", callback_data="add_new")]]
    
    reply_markup = create_paginated_keyboard(
        items=ponds, page=page, page_size=5,
        button_text_formatter=lambda p: f"{'✅' if p.is_active else '☑️'} {p.name}",
        button_callback_formatter=lambda p: f"select_{p.id}",
        pagination_callback_prefix="ponds_page_",
        extra_buttons=extra_buttons
    )
    
    text = "Управление водоёмами:"
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    return PondState.MENU

async def select_pond_for_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    """Обрабатывает выбор водоёма из списка."""
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]
    return await _display_pond_actions(pond_id, update, context)

async def toggle_pond_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    """Переключает статус активности водоёма."""
    query = update.callback_query
    await query.answer()
    pond_id = context.user_data['selected_pond_id']
    pond = references.get_pond_by_id(pond_id)
    
    if not pond:
        await query.edit_message_text("Водоём не найден.")
        return await ponds_start(update, context, clear_selection=True)

    success = references.update_pond_status(pond_id, not pond.is_active)
    if success:
        await query.edit_message_text("✅ Статус водоёма успешно изменен.")
    else:
        await query.edit_message_text("❌ Ошибка при изменении статуса.")
    
    return await ponds_start(update, context)

# --- Сценарий добавления нового водоёма ---
async def add_pond_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    query = update.callback_query
    await query.answer()
    # Use 'pond_id' as the key to be consistent
    context.user_data['new_pond_data'] = {'pond_id': f"POND-{uuid.uuid4().hex[:6].upper()}"} 
    await query.edit_message_text("<b>Шаг 1/6:</b> Введите название нового водоёма:", parse_mode='HTML')
    return PondState.ADD_NAME

async def add_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    context.user_data['new_pond_data']['name'] = update.message.text.strip()
    keyboard = [[
        InlineKeyboardButton("Пруд", callback_data="type_pond"),
        InlineKeyboardButton("Бассейн", callback_data="type_pool"),
        InlineKeyboardButton("Другой", callback_data="type_other"),
    ]]
    await update.message.reply_text("<b>Шаг 2/6:</b> Выберите тип водоёма:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return PondState.ADD_TYPE

async def add_type_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    query = update.callback_query
    await query.answer()
    context.user_data['new_pond_data']['type'] = query.data.split("_")[1]
    await query.edit_message_text("<b>Шаг 3/6:</b> Введите вид рыбы (например, Карп, Форель). Если не известно, напишите 'нет':", parse_mode='HTML')
    return PondState.ADD_SPECIES

### НАЧАЛО ИСПРАВЛЕНИЯ: Восстановленные и обновленные функции ###
async def add_species_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    species = update.message.text.strip()
    context.user_data['new_pond_data']['species'] = species if species.lower() != 'нет' else None
    await update.message.reply_text("<b>Шаг 4/6:</b> Введите дату зарыбления в формате ГГГГ-ММ-ДД. Если не известно, напишите 'нет':", parse_mode='HTML')
    return PondState.ADD_STOCKING_DATE

async def add_stocking_date_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    date_str = update.message.text.strip()
    if date_str.lower() == 'нет':
        context.user_data['new_pond_data']['stocking_date'] = None
    else:
        try:
            context.user_data['new_pond_data']['stocking_date'] = date.fromisoformat(date_str)
        except ValueError:
            await update.message.reply_text("❗️Неверный формат даты. Используйте ГГГГ-ММ-ДД или 'нет'.")
            return PondState.ADD_STOCKING_DATE
            
    await update.message.reply_text("<b>Шаг 5/6:</b> Введите начальное количество рыбы (шт). Если не известно, напишите 'нет':", parse_mode='HTML')
    return PondState.ADD_INITIAL_QTY

async def add_initial_qty_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    qty_str = update.message.text.strip()
    if qty_str.lower() == 'нет':
        context.user_data['new_pond_data']['initial_qty'] = None
    else:
        try:
            qty = int(qty_str)
            if qty < 0: raise ValueError("Количество не может быть отрицательным.")
            context.user_data['new_pond_data']['initial_qty'] = qty
        except (ValueError, TypeError):
            await update.message.reply_text("❗️Неверный формат. Введите целое положительное число или 'нет'.")
            return PondState.ADD_INITIAL_QTY
            
    await update.message.reply_text("<b>Шаг 6/6:</b> Введите любые заметки о водоёме. Если нет, напишите 'нет':", parse_mode='HTML')
    return PondState.ADD_NOTES
### КОНЕЦ ИСПРАВЛЕНИЯ ###

async def add_notes_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    notes = update.message.text
    context.user_data['new_pond_data']['notes'] = notes if notes.lower() != 'нет' else ""
    data = context.user_data['new_pond_data']
    summary = (
        f"<b>Подтвердите данные нового водоёма:</b>\n\n"
        f"<b>Название:</b> {data['name']}\n<b>Тип:</b> {data['type']}\n"
        f"<b>Вид рыбы:</b> {data.get('species') or 'не указан'}\n"
        f"<b>Дата зарыбления:</b> {data.get('stocking_date').isoformat() if data.get('stocking_date') else 'не указана'}\n"
        f"<b>Нач. кол-во:</b> {data.get('initial_qty') or 'не указано'}\n<b>Заметки:</b> {data['notes'] or 'нет'}\n"
        f"<b>Статус:</b> Активен"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Сохранить", callback_data="save_new"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return PondState.CONFIRM_ADD

async def save_new_pond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    query = update.callback_query
    await query.answer()
    try:
        data = context.user_data.pop('new_pond_data', {})
        # This now correctly matches the dictionary key and the model field
        pond = Pond(
            pond_id=data['pond_id'], name=data['name'], type=data['type'], 
            species=data.get('species'), stocking_date=data.get('stocking_date'),
            initial_qty=data.get('initial_qty'), notes=data.get('notes', ''), is_active=True
        )
        logs.append_pond(pond)
        references.get_all_ponds.cache_clear()
        await query.edit_message_text(f"✅ Водоём '{pond.name}' успешно добавлен.")
    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка: {e}")
    
    await _cleanup_temp_data(context)
    return await ponds_start(update, context)

# --- Сценарий редактирования ---
async def edit_pond_data_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    query = update.callback_query
    await query.answer()
    pond_id = context.user_data['selected_pond_id']
    
    keyboard = [
        [InlineKeyboardButton("Название", callback_data="edit_name")],
        [InlineKeyboardButton("Тип", callback_data="edit_type")],
        [InlineKeyboardButton("Вид рыбы", callback_data="edit_species")],
        [InlineKeyboardButton("Дату зарыбления", callback_data="edit_stocking_date")],
        [InlineKeyboardButton("Нач. кол-во", callback_data="edit_initial_qty")],
        [InlineKeyboardButton("Заметки", callback_data="edit_notes")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_actions_{pond_id}")]
    ]
    await query.edit_message_text(f"Что хотите отредактировать?", reply_markup=InlineKeyboardMarkup(keyboard))
    return PondState.SELECT_EDIT_FIELD

async def ask_for_new_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    query = update.callback_query
    await query.answer()
    field_name = query.data.split("_")[1]
    context.user_data['edit_field_name'] = field_name
    
    prompts = {
        'name': "Введите новое название:", 'type': "Выберите новый тип водоёма:",
        'species': "Введите новый вид рыбы (или 'нет'):",
        'stocking_date': "Введите новую дату (ГГГГ-ММ-ДД или 'нет'):",
        'initial_qty': "Введите новое начальное кол-во (или 'нет'):",
        'notes': "Введите новые заметки (или 'нет'):"
    }
    
    if field_name == 'type':
        keyboard = [[
            InlineKeyboardButton("Пруд", callback_data="new_val_pond"),
            InlineKeyboardButton("Бассейн", callback_data="new_val_pool"),
            InlineKeyboardButton("Другой", callback_data="new_val_other"),
        ]]
        await query.edit_message_text(prompts[field_name], reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text(prompts[field_name])
        
    return PondState.EDIT_FIELD_VALUE

async def receive_and_update_field_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> PondState:
    pond_id = context.user_data['selected_pond_id']
    field_name = context.user_data.pop('edit_field_name', None)
    if not field_name:
        return await _display_pond_actions(pond_id, update, context)

    new_value_raw = ""
    source_message = None
    if update.callback_query:
        await update.callback_query.answer()
        new_value_raw = update.callback_query.data.split("new_val_")[1]
        source_message = update.callback_query.message
    elif update.message:
        new_value_raw = update.message.text.strip()
        source_message = update.message
    
    try:
        new_value = new_value_raw
        if new_value_raw.lower() == 'нет' and field_name not in ['name', 'type', 'notes']:
            new_value = None
        elif new_value_raw.lower() == 'нет' and field_name == 'notes':
            new_value = ""
        elif field_name == 'stocking_date':
            # Приводим к date, чтобы проверить формат, но храним как строку
            new_value = date.fromisoformat(new_value_raw).isoformat()
        elif field_name == 'initial_qty':
            qty = int(new_value_raw)
            if qty < 0: raise ValueError("Количество не может быть отрицательным.")
            new_value = qty
        
        success = references.update_pond_details(pond_id, field_name, new_value)
        if not success: raise Exception("Ошибка записи в таблицу.")
        
        reply_message = f"✅ Поле '{field_name}' успешно обновлено."

    except ValueError as e:
        reply_message = f"❗️Неверный формат или значение: {e}. Попробуйте снова."
        # --- ИСПРАВЛЕНИЕ: Отправляем сообщение об ошибке здесь ---
        await source_message.reply_text(reply_message)
        # Возвращаем пользователя на тот же шаг для повторного ввода
        context.user_data['edit_field_name'] = field_name # <-- Важно вернуть поле обратно
        return PondState.EDIT_FIELD_VALUE
    except Exception as e:
        reply_message = f"❌ Произошла ошибка: {e}"

    # Этот блок теперь выполняется только при успехе
    await source_message.reply_text(reply_message)
    return await _display_pond_actions(pond_id, update, context)

# --- ConversationHandler ---
ponds_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.MANAGE_PONDS), ponds_start)],
    states={
        PondState.MENU: [
            CallbackQueryHandler(select_pond_for_action, pattern="^select_"),
            CallbackQueryHandler(add_pond_start, pattern="^add_new$"),
            CallbackQueryHandler(ponds_start, pattern="^ponds_page_")
        ],
        PondState.SELECT_ACTION: [
            CallbackQueryHandler(toggle_pond_status, pattern="^toggle_status$"),
            CallbackQueryHandler(edit_pond_data_start, pattern="^edit_data$"),
            CallbackQueryHandler(ponds_start, pattern="^back_to_list$")
        ],
        # Сценарий добавления
        PondState.ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name_received)],
        PondState.ADD_TYPE: [CallbackQueryHandler(add_type_received, pattern="^type_")],
        PondState.ADD_SPECIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_species_received)],
        PondState.ADD_STOCKING_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_stocking_date_received)],
        PondState.ADD_INITIAL_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_initial_qty_received)],
        PondState.ADD_NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_notes_received)],
        PondState.CONFIRM_ADD: [
            CallbackQueryHandler(save_new_pond, pattern="^save_new$"),
            CallbackQueryHandler(ponds_start, pattern="^cancel_add$")
        ],
        # Сценарий редактирования
        PondState.SELECT_EDIT_FIELD: [
            CallbackQueryHandler(ask_for_new_field_value, pattern="^edit_"),
            CallbackQueryHandler(select_pond_for_action, pattern=r"^back_to_actions_")
        ],
        PondState.EDIT_FIELD_VALUE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_and_update_field_value),
            CallbackQueryHandler(receive_and_update_field_value, pattern="^new_val_")
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)