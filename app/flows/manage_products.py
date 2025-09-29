# flows/manage_products.py
from app.bot.keyboards import ReplyButton
import uuid
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler, CallbackQueryHandler, MessageHandler, filters
)

from app.bot.middleware import restricted
from app.models.user import UserRole
from app.models.product import Product
from app.sheets import references, logs
from app.bot.keyboards import create_paginated_keyboard
from .common import cancel

# --- ИЗМЕНЕНИЕ: Состояния диалога заменены на Enum ---
class ProductState(Enum):
    MENU = auto()
    SELECT_ACTION = auto()
    SELECT_EDIT_FIELD = auto()
    EDIT_FIELD_VALUE = auto()
    # Состояния для добавления нового товара
    ADD_NAME = auto()
    ADD_DESC = auto()
    ADD_PRICE = auto()
    ADD_UNIT = auto()
    CONFIRM_ADD = auto()

# --- Вспомогательные функции ---

async def _display_product_actions(product_id: str, update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Отображает детали товара и меню действий (редактировать, изменить статус)."""
    product = references.get_product_by_id(product_id)
    if not product:
        text = "Товар не найден. Возможно, он был удален."
        if update.callback_query:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return await products_start(update, context, clear_selection=True)

    context.user_data['selected_product_id'] = product_id
    status_text = "Доступен для заказа" if product.is_available else "Не доступен для заказа"
    toggle_text = "Сделать недоступным" if product.is_available else "Сделать доступным"
    
    keyboard = [
        [InlineKeyboardButton(f"🔄 {toggle_text}", callback_data="toggle_status")],
        [InlineKeyboardButton("📝 Редактировать данные", callback_data="edit_data")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="back_to_list")]
    ]
    
    details_text = (
        f"<b>Товар:</b> {product.name}\n"
        f"<b>Описание:</b> {product.description}\n"
        f"<b>Цена:</b> {product.get_display_price()}\n"
        f"<b>Статус:</b> {status_text}"
    )

    if update.callback_query:
        await update.callback_query.edit_message_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    else:
        await update.message.reply_text(details_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    return ProductState.SELECT_ACTION

async def _cleanup_temp_data(context: ContextTypes.DEFAULT_TYPE):
    """Безопасно очищает временные данные, сохраняя сессию пользователя."""
    keys_to_remove = ['new_product', 'selected_product_id', 'edit_field']
    for key in keys_to_remove:
        if key in context.user_data:
            del context.user_data[key]

# --- Основные обработчики диалога ---

@restricted(allowed_roles=[UserRole.ADMIN])
async def products_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Отображает главный список товаров с пагинацией (БЕЗ логики очистки)."""
    query = update.callback_query
    page = 0

    if query:
        await query.answer()
        if query.data.startswith("products_page_"):
            page = int(query.data.split("_")[2])

    products = references.get_all_products()
    
    extra_buttons = [[InlineKeyboardButton("➕ Добавить новый товар", callback_data="add_new")]]
    
    reply_markup = create_paginated_keyboard(
        items=products, page=page, page_size=5,
        button_text_formatter=lambda p: f"{'✅' if p.is_available else '☑️'} {p.name}",
        button_callback_formatter=lambda p: f"select_{p.id}",
        pagination_callback_prefix="products_page_",
        extra_buttons=extra_buttons
    )
    
    text = "Управление товарами:"
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    return ProductState.MENU

async def back_to_product_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Очищает ID выбранного товара и переходит к общему списку."""
    if 'selected_product_id' in context.user_data:
        del context.user_data['selected_product_id']
    
    # Теперь вызываем основную функцию для отображения списка
    return await products_start(update, context)

async def select_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Обрабатывает выбор товара из списка."""
    query = update.callback_query
    await query.answer()
    product_id = query.data.split("_")[1]
    return await _display_product_actions(product_id, update, context)

async def toggle_product_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Переключает статус доступности товара."""
    query = update.callback_query
    await query.answer()
    prod_id = context.user_data['selected_product_id']
    product = references.get_product_by_id(prod_id)
    
    success = references.update_product_status(prod_id, not product.is_available)
    if success:
        await query.edit_message_text("✅ Статус товара успешно изменен.")
    else:
        await query.edit_message_text("❌ Ошибка при изменении статуса.")
    
    return await products_start(update, context)

# --- Сценарий редактирования ---
async def edit_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    query = update.callback_query
    await query.answer()
    prod_id = context.user_data['selected_product_id']
    keyboard = [
        [InlineKeyboardButton("Название", callback_data="edit_name")],
        [InlineKeyboardButton("Описание", callback_data="edit_description")],
        [InlineKeyboardButton("Цену", callback_data="edit_price")],
        [InlineKeyboardButton("Ед. изм.", callback_data="edit_unit")],
        [InlineKeyboardButton("⬅️ Назад", callback_data=f"back_to_actions_{prod_id}")]
    ]
    await query.edit_message_text("Что вы хотите отредактировать?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ProductState.SELECT_EDIT_FIELD

async def ask_for_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    query = update.callback_query
    await query.answer()
    field = query.data.split("_")[1]
    context.user_data['edit_field'] = field
    prompts = {
        'name': "Введите новое название:", 'description': "Введите новое описание:",
        'price': "Введите новую цену (например, 150.50):", 'unit': "Введите новую единицу измерения (например, кг):"
    }
    await query.edit_message_text(prompts.get(field, "Введите новое значение:"))
    return ProductState.EDIT_FIELD_VALUE

async def save_edited_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    """Получает новое значение, обновляет его и возвращает к карточке товара."""
    field = context.user_data.pop('edit_field', None)
    prod_id = context.user_data['selected_product_id']
    if not field:
        return await _display_product_actions(prod_id, update, context)

    new_value_raw = update.message.text.strip()
    if not new_value_raw:
        await update.message.reply_text("Значение не может быть пустым. Попробуйте снова.")
        context.user_data['edit_field'] = field # Возвращаем поле для повторной попытки
        return ProductState.EDIT_FIELD_VALUE

    try:
        new_value = new_value_raw
        if field == 'price':
            price = float(new_value_raw.replace(',', '.'))
            if price <= 0: raise ValueError("Цена должна быть положительной.")
            new_value = price
        
        success = references.update_product_details(prod_id, field, new_value)
        if not success: raise Exception("Ошибка записи в таблицу.")
        
        await update.message.reply_text(f"✅ Поле '{field}' успешно обновлено.")
            
    except (ValueError, TypeError):
        await update.message.reply_text(f"❗️Неверный формат. Цена должна быть числом. Попробуйте снова.")
        context.user_data['edit_field'] = field
        return ProductState.EDIT_FIELD_VALUE
    except Exception as e:
        await update.message.reply_text(f"❌ Произошла ошибка: {e}")

    return await _display_product_actions(prod_id, update, context)

# --- Сценарий добавления нового товара ---
async def add_product_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("<b>Шаг 1/4:</b> Введите название нового товара:", parse_mode='HTML')
    return ProductState.ADD_NAME

async def add_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    name = update.message.text.strip()
    if not name:
        await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз.")
        return ProductState.ADD_NAME
    context.user_data['new_product'] = {'name': name}
    await update.message.reply_text("<b>Шаг 2/4:</b> Отлично. Теперь введите описание товара:", parse_mode='HTML')
    return ProductState.ADD_DESC

async def add_desc_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    desc = update.message.text.strip()
    if not desc:
        await update.message.reply_text("Описание не может быть пустым. Попробуйте еще раз.")
        return ProductState.ADD_DESC
    context.user_data['new_product']['description'] = desc
    await update.message.reply_text("<b>Шаг 3/4:</b> Теперь введите цену (например, 150.50):", parse_mode='HTML')
    return ProductState.ADD_PRICE

async def add_price_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    try:
        price = float(update.message.text.replace(',', '.'))
        if price <= 0: raise ValueError
        context.user_data['new_product']['price'] = price
        await update.message.reply_text("<b>Шаг 4/4:</b> Последний шаг: введите единицу измерения (например, кг, шт):", parse_mode='HTML')
        return ProductState.ADD_UNIT
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите положительное число.")
        return ProductState.ADD_PRICE

async def add_unit_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    unit = update.message.text.strip()
    if not unit:
        await update.message.reply_text("Единица измерения не может быть пустой. Попробуйте еще раз.")
        return ProductState.ADD_UNIT
    context.user_data['new_product']['unit'] = unit
    data = context.user_data['new_product']
    summary = (
        f"<b>Подтвердите данные нового товара:</b>\n\n"
        f"<b>Название:</b> {data['name']}\n"
        f"<b>Описание:</b> {data['description']}\n"
        f"<b>Цена:</b> {data['price']:.2f} грн\n"
        f"<b>Ед.изм.:</b> {data['unit']}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Сохранить", callback_data="save_new"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_add")
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return ProductState.CONFIRM_ADD

async def save_new_product(update: Update, context: ContextTypes.DEFAULT_TYPE) -> ProductState:
    query = update.callback_query
    await query.answer()
    try:
        data = context.user_data.pop('new_product', {})
        product = Product(
            product_id=f"PROD-{uuid.uuid4().hex[:6].upper()}",
            name=data['name'], description=data['description'],
            price=data['price'], unit=data['unit'], is_available=True
        )
        logs.append_product(product)
        references.get_all_products.cache_clear()
        await query.edit_message_text(f"✅ Товар '{product.name}' успешно добавлен.")
    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка: {e}")
    
    await _cleanup_temp_data(context) # <-- ИЗМЕНЕНИЕ: Безопасная очистка
    return await products_start(update, context)

# --- ConversationHandler ---
products_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.MANAGE_PRODUCTS), products_start)],
    states={
        ProductState.MENU: [
            CallbackQueryHandler(select_product, pattern="^select_"),
            CallbackQueryHandler(add_product_start, pattern="^add_new$"),
            CallbackQueryHandler(products_start, pattern="^products_page_")
        ],
        ProductState.SELECT_ACTION: [
            CallbackQueryHandler(toggle_product_status, pattern="^toggle_status$"),
            CallbackQueryHandler(edit_product_start, pattern="^edit_data$"),
            CallbackQueryHandler(back_to_product_list, pattern="^back_to_list$")
        ],
        # Сценарий добавления
        ProductState.ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_name_received)],
        ProductState.ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc_received)],
        ProductState.ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_price_received)],
        ProductState.ADD_UNIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_unit_received)],
        ProductState.CONFIRM_ADD: [
            CallbackQueryHandler(save_new_product, pattern="^save_new$"),
            CallbackQueryHandler(products_start, pattern="^cancel_add$")
        ],
        # Сценарий редактирования
        ProductState.SELECT_EDIT_FIELD: [
            CallbackQueryHandler(ask_for_new_value, pattern="^edit_"),
            CallbackQueryHandler(select_product, pattern=r"^back_to_actions_")
        ],
        ProductState.EDIT_FIELD_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edited_value)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)