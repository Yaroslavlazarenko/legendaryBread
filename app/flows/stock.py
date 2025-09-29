# app/flows/stock.py

"""
Этот модуль содержит ConversationHandler для управления складскими операциями с кормами.

Сценарий работы:
1. Пользователь запускает команду /stock.
2. Бот предлагает выбрать тип корма из справочника.
3. Бот предлагает выбрать тип операции: "Приход" или "Расход".
4. Бот запрашивает массу корма в килограммах.
5. Бот запрашивает причину или комментарий к операции.
6. Бот показывает сводку данных и просит подтвердить сохранение.
7. После подтверждения данные записываются в лог складских операций.
"""
from app.bot.keyboards import ReplyButton
from datetime import datetime
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from app.bot.middleware import restricted
from app.models.user import UserRole
from app.models.stock import StockMoveRow, StockMoveType
from app.sheets import references, logs
from .common import cancel


class StockState(Enum):
    """Состояния для диалога складских операций."""
    SELECT_FEED = auto()
    SELECT_TYPE = auto()
    ENTER_MASS = auto()
    ENTER_REASON = auto()
    CONFIRM = auto()


@restricted(allowed_roles=[UserRole.ADMIN, UserRole.OPERATOR])
async def stock_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> StockState | int:
    """
    Начинает диалог складской операции, запрашивая тип корма.
    """
    feed_types = references.get_active_feed_types()
    if not feed_types:
        await update.message.reply_text("В системе нет активных типов кормов. Обратитесь к администратору.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(ft.name, callback_data=f"feed_{ft.id}")] for ft in feed_types]
    await update.message.reply_text("Выберите тип корма для складской операции:", reply_markup=InlineKeyboardMarkup(keyboard))
    return StockState.SELECT_FEED


async def feed_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> StockState | int:
    """
    Обрабатывает выбор корма и запрашивает тип операции (приход/расход).
    """
    query = update.callback_query
    await query.answer()
    feed_id = query.data.split("_")[1]
    feed_type = next((ft for ft in references.get_active_feed_types() if ft.id == feed_id), None)
    if not feed_type:
        await query.edit_message_text("Ошибка: тип корма не найден.")
        return ConversationHandler.END
    context.user_data['stock_feed'] = feed_type

    keyboard = [
        [InlineKeyboardButton("⬆️ Приход на склад", callback_data=f"type_{StockMoveType.INCOME.value}")],
        [InlineKeyboardButton("⬇️ Расход со склада", callback_data=f"type_{StockMoveType.OUTCOME.value}")]
    ]
    await query.edit_message_text(f"Корм: {feed_type.name}.\nВыберите тип операции:", reply_markup=InlineKeyboardMarkup(keyboard))
    return StockState.SELECT_TYPE


async def type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> StockState:
    """
    Обрабатывает выбор типа операции и запрашивает массу.
    """
    query = update.callback_query
    await query.answer()
    context.user_data['stock_move_type'] = StockMoveType(query.data.split("_")[1])
    await query.edit_message_text("Введите массу в кг (например, 1500.5):")
    return StockState.ENTER_MASS


async def mass_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> StockState:
    """
    Принимает массу и запрашивает причину операции.
    """
    try:
        mass = float(update.message.text.replace(',', '.'))
        if mass <= 0:
            raise ValueError("Масса должна быть положительным числом.")
        context.user_data['stock_mass'] = mass
        await update.message.reply_text("Введите причину/комментарий (например, 'Закупка по накладной #123', 'Списание по акту'):")
        return StockState.ENTER_REASON
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите положительное число.")
        return StockState.ENTER_MASS


async def reason_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> StockState:
    """
    Принимает причину, формирует сводку и запрашивает подтверждение.
    """
    context.user_data['stock_reason'] = update.message.text

    feed = context.user_data['stock_feed']
    move_type = context.user_data['stock_move_type']
    mass = context.user_data['stock_mass']
    reason = context.user_data['stock_reason']

    summary = (
        f"<b>Подтвердите операцию:</b>\n\n"
        f"<b>Корм:</b> {feed.name}\n"
        f"<b>Операция:</b> {'Приход' if move_type == StockMoveType.INCOME else 'Расход'}\n"
        f"<b>Масса:</b> {mass} кг\n"
        f"<b>Причина:</b> {reason}"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Сохранить", callback_data="save"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_op")
    ]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return StockState.CONFIRM


async def save_stock_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Сохраняет данные о складской операции в лог.
    """
    query = update.callback_query
    await query.answer()
    try:
        row = StockMoveRow(
            ts=datetime.now(),
            feed_type_id=context.user_data['stock_feed'].id,
            feed_type_name=context.user_data['stock_feed'].name,
            move_type=context.user_data['stock_move_type'],
            mass_kg=context.user_data['stock_mass'],
            reason=context.user_data['stock_reason'],
            user=f"{context.user_data['current_user'].name} ({context.user_data['current_user'].id})"
        )
        logs.append_stock_move(row)
        await query.edit_message_text("✅ Складская операция успешно сохранена.")
    except Exception as e:
        await query.edit_message_text(f"❌ Произошла ошибка при сохранении: {e}")
    finally:
        context.user_data.clear()

    return ConversationHandler.END


# Определяем обработчик диалога для складских операций
stock_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.STOCK_CONTROL), stock_start)],
    states={
        StockState.SELECT_FEED: [CallbackQueryHandler(feed_selected, pattern="^feed_")],
        StockState.SELECT_TYPE: [CallbackQueryHandler(type_selected, pattern="^type_")],
        StockState.ENTER_MASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, mass_received)],
        StockState.ENTER_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, reason_received)],
        StockState.CONFIRM: [
            CallbackQueryHandler(save_stock_move, pattern="^save$"),
            CallbackQueryHandler(cancel, pattern="^cancel_op$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)