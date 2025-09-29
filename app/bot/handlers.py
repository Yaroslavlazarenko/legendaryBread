from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler # <-- Добавьте MessageHandler и filters

from app.bot.middleware import restricted
from app.models.user import UserRole
from app.bot.keyboards import create_main_menu_keyboard, ReplyButton # <-- Импортируем нашу новую функцию и константы

# Импортируем все Conversation Handlers
from app.flows.registration import registration_conv_handler
from app.flows.admin import admin_conv_handler
from app.flows.manage_products import products_conv_handler
from app.flows.manage_ponds import ponds_conv_handler
from app.flows.manage_feed_types import manage_feed_types_conv_handler
from app.flows.stock import stock_conv_handler
from app.flows.operator import (
    water_quality_conv_handler, 
    feeding_conv_handler,
    weighing_conv_handler,
    fish_move_conv_handler
)
from app.flows.client import catalog_start, client_order_conv_handler
from app.flows.common import handle_expired_callback
from app.flows.settings import show_notification_settings, notifications_callback_handler, back_to_main_menu_handler

@restricted(allowed_roles=[UserRole.ADMIN, UserRole.OPERATOR, UserRole.CLIENT], self_register=True)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение и показывает главное меню в виде клавиатуры."""
    user = context.user_data.get('current_user')
    if not user: return

    reply_markup = create_main_menu_keyboard(user.role)
    
    text = (
        f"Привет, {user.name}! Ваша роль: {user.role.value}.\n\n"
        "Используйте кнопки ниже для навигации."
    )
    if user.role == UserRole.ADMIN:
        text += "\n\nДля настройки уведомлений используйте /notifications"


    await update.message.reply_text(text, reply_markup=reply_markup)

def register_handlers(application: Application) -> None:
    """Регистрирует все обработчики в приложении."""
    # Базовые команды
    application.add_handler(CommandHandler("start", start))
    
    # Регистрация остается по команде, т.к. для незарегистрированных пользователей кнопок нет
    application.add_handler(registration_conv_handler)
    
    # Обработчики для кнопок, которые не являются диалогами
    application.add_handler(MessageHandler(filters.Text(ReplyButton.CATALOG), catalog_start))
    application.add_handler(MessageHandler(filters.Text(ReplyButton.SETTINGS), show_notification_settings))

    # Диалоги (ConversationHandlers), запускаемые кнопками
    # Административные
    application.add_handler(notifications_callback_handler)
    application.add_handler(admin_conv_handler)
    application.add_handler(products_conv_handler)
    application.add_handler(ponds_conv_handler)
    application.add_handler(manage_feed_types_conv_handler)
    application.add_handler(stock_conv_handler)
    application.add_handler(back_to_main_menu_handler)
    
    # Операторские
    application.add_handler(water_quality_conv_handler)
    application.add_handler(feeding_conv_handler)
    application.add_handler(weighing_conv_handler)
    application.add_handler(fish_move_conv_handler)
    
    # Клиентские
    application.add_handler(client_order_conv_handler)

    application.add_handler(CallbackQueryHandler(handle_expired_callback))