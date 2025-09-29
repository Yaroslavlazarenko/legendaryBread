# app/flows/admin.py

from enum import Enum, auto
from app.bot.keyboards import ReplyButton
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
from app.bot.middleware import restricted
from app.bot.keyboards import create_paginated_keyboard, create_main_menu_keyboard, ReplyButton
from app.models.user import User, UserRole
from app.sheets import references
from app.utils.logger import log
from .common import cancel

class AdminState(Enum):
    ADMIN_MENU = auto()
    USER_MENU = auto()
    USER_LIST = auto()
    USER_ACTIONS = auto()
    ORDER_LIST = auto()
    ORDER_DETAILS = auto()
    SELECT_ROLE = auto()


@restricted(allowed_roles=[UserRole.ADMIN])
async def admin_panel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Отображает главное меню администратора."""
    keyboard = [
        [InlineKeyboardButton("👤 Управление пользователями", callback_data="goto_users")],
        [InlineKeyboardButton("📦 Управление заказами", callback_data="goto_orders")],
        [InlineKeyboardButton("↩️ Выход", callback_data="exit")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Панель администратора:"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        # This check is needed because the entry point is a CommandHandler
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup)
        
    return AdminState.ADMIN_MENU

# === ВЕТКА УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ ===

async def show_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Меню выбора действий с пользователями."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("⏳ Подтвердить новых", callback_data="users_pending")],
        [InlineKeyboardButton("👥 Управлять существующими", callback_data="users_manage")],
        [InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]
    ]
    await query.edit_message_text("Управление пользователями:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AdminState.USER_MENU

async def show_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    query = update.callback_query
    page = 0
    
    # Logic to extract page and list_type from callback_data
    parts = query.data.split('_')
    list_type = parts[1]
    if len(parts) > 2 and parts[2] == 'page':
        page = int(parts[3])

    await query.answer()
    context.user_data['user_list_type'] = list_type
    
    all_users = references.get_all_users()
    if list_type == "pending":
        users_to_show = [u for u in all_users if u.role == UserRole.PENDING]
        message_text = "Выберите пользователя для подтверждения:"
        if not users_to_show: message_text = "Нет пользователей, ожидающих подтверждения."
    else: # 'manage'
        users_to_show = [u for u in all_users if u.role != UserRole.PENDING]
        message_text = "Выберите пользователя для управления:"
        if not users_to_show: message_text = "Нет зарегистрированных пользователей."
            
    extra_buttons = [[InlineKeyboardButton("⬅️ Назад", callback_data="goto_users")]]
    reply_markup = create_paginated_keyboard(
        items=users_to_show, page=page, page_size=5,
        # Corrected: Use u.name and u.id
        button_text_formatter=lambda u: f"{u.name} ({u.role.value})",
        button_callback_formatter=lambda u: f"user_{u.id}",
        pagination_callback_prefix=f"users_{list_type}_page_",
        extra_buttons=extra_buttons
    )
    
    await query.edit_message_text(message_text, reply_markup=reply_markup)
    return AdminState.USER_LIST

async def show_user_actions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Показывает меню действий для выбранного пользователя."""
    query = update.callback_query
    await query.answer()
    
    # NEW LOGIC: Get user_id from query.data if it's a new selection,
    # otherwise, use the one already stored in the context.
    if query.data.startswith("user_"):
        user_id = int(query.data.split("_")[1])
        context.user_data['selected_user_id'] = user_id
    else:
        user_id = context.user_data.get('selected_user_id')

    if not user_id:
        await query.edit_message_text("Ошибка: не удалось определить пользователя. Возврат в меню.")
        return await show_user_menu(update, context)
        
    user = references.get_user_by_id(user_id)

    if not user:
        await query.edit_message_text("Пользователь не найден.")
        return AdminState.USER_MENU

    block_text = "🔓 Разблокировать" if user.role == UserRole.BLOCKED else "🚫 Заблокировать"
    block_action = "unblock" if user.role == UserRole.BLOCKED else "block"

    keyboard = [
        [InlineKeyboardButton("🔄 Сменить роль", callback_data="action_changerole")],
        [InlineKeyboardButton(block_text, callback_data=f"action_{block_action}")],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data=f"users_{context.user_data.get('user_list_type', 'manage')}_page_0")]
    ]
    # Corrected: Use user.name
    await query.edit_message_text(
        f"Управление: {user.name}\nТекущая роль: {user.role.value}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return AdminState.USER_ACTIONS

async def ask_for_role_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Показывает кнопки для выбора новой роли."""
    query = update.callback_query
    await query.answer()
    user = references.get_user_by_id(context.user_data['selected_user_id'])
    
    keyboard = [
        [InlineKeyboardButton(r.value.capitalize(), callback_data=f"role_{r.value}")]
        for r in UserRole if r not in [UserRole.PENDING, UserRole.BLOCKED, user.role]
    ]
    # Corrected: Use user.id
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data=f"user_{user.id}")])
    # Corrected: Use user.name
    await query.edit_message_text(f"Выберите новую роль для {user.name}:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AdminState.SELECT_ROLE
    
async def update_user_role(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Обновляет роль и уведомляет пользователя, предоставляя ему новое меню."""
    query = update.callback_query
    await query.answer()
    user_id = context.user_data['selected_user_id']
    
    if query.data.startswith("action_"):
        action = query.data.split("_")[1]
        # При разблокировке по умолчанию ставим роль КЛИЕНТ
        new_role = UserRole.BLOCKED if action == "block" else UserRole.CLIENT
    else:
        new_role_str = query.data.split("_")[1]
        new_role = UserRole(new_role_str)
        
    success = references.update_user_role(user_id, new_role)
    
    if success:
        user = references.get_user_by_id(user_id)
        success_text = f"✅ Пользователю {user.name} назначена роль: {new_role.value}"
        
        # --- НАЧАЛО ИЗМЕНЕНИЙ В ЛОГИКЕ УВЕДОМЛЕНИЯ ---
        try:
            # Если роль активна (пользователя подтвердили, разблокировали или сменили роль)
            if new_role in [UserRole.ADMIN, UserRole.CLIENT, UserRole.OPERATOR]:
                message_to_user = (
                    f"Ваша учетная запись обновлена! ✨\n\n"
                    f"Ваша новая роль: <b>{new_role.value}</b>.\n\n"
                    f"Используйте меню ниже для навигации."
                )
                new_keyboard = create_main_menu_keyboard(new_role)
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=message_to_user, 
                    reply_markup=new_keyboard,
                    parse_mode='HTML'
                )

            # Если пользователя заблокировали
            elif new_role == UserRole.BLOCKED:
                message_to_user = "Ваш доступ к системе был заблокирован администратором."
                await context.bot.send_message(
                    chat_id=user_id, 
                    text=message_to_user, 
                    reply_markup=ReplyKeyboardRemove() # Удаляем клавиатуру
                )

        except Exception as e:
            log.warning(f"Не удалось уведомить пользователя {user_id}: {e}")
            success_text += "\n⚠️ Не удалось уведомить пользователя."
        # --- КОНЕЦ ИЗМЕНЕНИЙ В ЛОГИКЕ УВЕДОМЛЕНИЯ ---
            
        await query.edit_message_text(success_text)

    else:
        await query.edit_message_text("❌ Произошла ошибка при обновлении роли.")
    
    return await show_user_actions(update, context)

# === ВЕТКА УПРАВЛЕНИЯ ЗАКАЗАМИ ===

async def show_new_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Показывает список новых заказов."""
    query = update.callback_query
    await query.answer()
    
    new_orders = references.get_orders_by_status("new")
    if not new_orders:
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")]]
        await query.edit_message_text("Нет новых заказов для обработки.", reply_markup=InlineKeyboardMarkup(keyboard))
        return AdminState.ADMIN_MENU

    keyboard = [
        [InlineKeyboardButton(
            f"#{o.id.split('-')[1]} от {o.client_name} ({o.total_amount:.2f} грн)",
            callback_data=f"order_{o.id}"
        )] for o in new_orders
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="back_to_admin_menu")])
    await query.edit_message_text("Новые заказы:", reply_markup=InlineKeyboardMarkup(keyboard))
    return AdminState.ORDER_LIST

async def show_order_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Показывает детали заказа и кнопки действий."""
    query = update.callback_query
    await query.answer()
    order_id = query.data.split("_")[1]
    context.user_data['selected_order_id'] = order_id
    
    # Use a more robust way to get the order, not relying on the "new" filter again
    all_orders = references.get_all_orders() # Assuming such a function exists or can be made
    order = next((o for o in all_orders if o.id == order_id), None)

    if not order:
        await query.edit_message_text("Заказ не найден или уже обработан.")
        return await show_new_orders(update, context)

    items = references.get_order_items(order_id)
    
    text = (
        f"<b>Заказ #{order.id.split('-')[1]}</b>\n\n"
        f"<b>Клиент:</b> {order.client_name}\n<b>Телефон:</b> {order.phone}\n\n"
        f"<b>Состав:</b>\n" +
        "".join([f" - {i.product_name}: {i.quantity} x {i.price_per_unit:.2f} грн\n" for i in items]) +
        f"\n<b>Итого: {order.total_amount:.2f} грн</b>"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="status_confirmed"),
            InlineKeyboardButton("❌ Отменить", callback_data="status_cancelled")
        ],
        [InlineKeyboardButton("⬅️ Назад к списку", callback_data="goto_orders")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return AdminState.ORDER_DETAILS

async def change_order_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> AdminState:
    """Меняет статус заказа и уведомляет клиента."""
    query = update.callback_query
    await query.answer()
    order_id = context.user_data['selected_order_id']
    new_status = query.data.split("_")[1]
    
    # Fetch the order BEFORE updating its status to ensure we can notify the client
    all_orders = references.get_all_orders()
    # FIX: Access the attribute by its correct Python name, 'id'
    order = next((o for o in all_orders if o.id == order_id), None)

    if not order:
        await query.edit_message_text("❌ Ошибка: Заказ не найден.")
        return await show_new_orders(update, context)

    success = references.update_order_status(order_id, new_status)
    if success:
        await query.edit_message_text(f"✅ Статус заказа #{order_id.split('-')[1]} изменен на '{new_status}'.")
        try:
            status_text = "подтвержден" if new_status == "confirmed" else "отменен"
            await context.bot.send_message(
                chat_id=order.client_id,
                text=f"Статус вашего заказа #{order_id.split('-')[1]} был изменен администратором на: <b>{status_text}</b>.",
                parse_mode='HTML'
            )
        except Exception as e:
            log.warning(f"Не удалось уведомить клиента {order.client_id} по заказу {order_id}: {e}")
    else:
        await query.edit_message_text("❌ Ошибка при смене статуса.")

    return await show_new_orders(update, context)

async def exit_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Вы вышли из панели администратора.")
    
    for key in ['user_list_type', 'selected_user_id', 'selected_order_id']:
         if key in context.user_data:
            del context.user_data[key]
            
    return ConversationHandler.END


admin_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.ADMIN_PANEL), admin_panel_start)],
    states={
        AdminState.ADMIN_MENU: [
            CallbackQueryHandler(show_user_menu, pattern="^goto_users$"),
            CallbackQueryHandler(show_new_orders, pattern="^goto_orders$"),
            CallbackQueryHandler(exit_admin_panel, pattern="^exit$"),
            # FIX: Add a handler for the 'back' button in this state
            CallbackQueryHandler(admin_panel_start, pattern="^back_to_admin_menu$"), 
        ],
        AdminState.USER_MENU: [
            CallbackQueryHandler(show_user_list, pattern="^users_(pending|manage)$"),
            CallbackQueryHandler(show_user_list, pattern="^users_(pending|manage)_page_"),
            CallbackQueryHandler(admin_panel_start, pattern="^back_to_admin_menu$"),
        ],
        AdminState.USER_LIST: [
            CallbackQueryHandler(show_user_actions, pattern="^user_"),
            CallbackQueryHandler(show_user_list, pattern="^users_(pending|manage)_page_"),
            CallbackQueryHandler(show_user_menu, pattern="^goto_users$"),
        ],
        AdminState.USER_ACTIONS: [
            CallbackQueryHandler(ask_for_role_change, pattern="^action_changerole$"),
            CallbackQueryHandler(update_user_role, pattern="^action_(un)?block$"),
            CallbackQueryHandler(show_user_list, pattern="^users_"),
        ],
        AdminState.SELECT_ROLE: [
            CallbackQueryHandler(update_user_role, pattern="^role_"),
            CallbackQueryHandler(show_user_actions, pattern="^user_"),
        ],
        AdminState.ORDER_LIST: [
            CallbackQueryHandler(show_order_details, pattern="^order_"),
            CallbackQueryHandler(admin_panel_start, pattern="^back_to_admin_menu$"),
        ],
        AdminState.ORDER_DETAILS: [
            CallbackQueryHandler(change_order_status, pattern="^status_"),
            CallbackQueryHandler(show_new_orders, pattern="^goto_orders$"),
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)