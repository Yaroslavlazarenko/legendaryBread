# app/flows/operator.py

from app.bot.keyboards import ReplyButton
from datetime import datetime
from enum import Enum, auto
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CommandHandler,
)
from app.bot.middleware import restricted
from app.models.user import UserRole
from app.models.water import WaterQualityRow
from app.models.feeding import FeedingRow
from app.models.weighing import WeighingRow
from app.models.fish import FishMoveRow, FishMoveType
from app.sheets import references, logs
from app.bot.notifications import notify_admins
from app.utils.logger import log
from .common import cancel, ask_for_pond_selection


class State(Enum):
    """
    Определяет состояния для всех диалогов ConversationHandler в этом модуле.
    """
    # Состояния для диалога замера воды
    SELECT_POND_W = auto()
    ENTER_DO = auto()
    ENTER_TEMP = auto()
    CONFIRM_WATER = auto()

    # Состояния для диалога кормления
    SELECT_POND_F = auto()
    SELECT_FEED = auto()
    ENTER_MASS_F = auto()
    CONFIRM_FEED = auto()

    # Состояния для диалога взвешивания
    SELECT_POND_WGH = auto()
    ENTER_WEIGHT = auto()
    CONFIRM_WEIGHING = auto()

    # Состояния для диалога движения рыбы
    SELECT_POND_FM_SRC = auto()
    SELECT_MOVE_TYPE = auto()
    SELECT_POND_FM_DEST = auto()
    ENTER_QUANTITY_FM = auto()
    ENTER_AVG_WEIGHT_FM = auto()
    ENTER_REASON_FM = auto()
    ENTER_REF_FM = auto()
    CONFIRM_FISH_MOVE = auto()


# === СЦЕНАРИЙ ЗАМЕРА ВОДЫ ===

@restricted(allowed_roles=[UserRole.OPERATOR, UserRole.ADMIN])
async def water_quality_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    if await ask_for_pond_selection(update, "Выберите водоём для замера параметров воды:"):
        return State.SELECT_POND_W
    return ConversationHandler.END


async def pond_selected_for_water(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]
    pond = next((p for p in references.get_active_ponds() if p.id == pond_id), None)
    if not pond:
        await query.edit_message_text("Ошибка: водоём не найден.")
        return ConversationHandler.END
    context.user_data['pond'] = pond
    await query.edit_message_text(f"Выбран водоём: {pond.name}.\n\nВведите значение DO, мг/л (например, 8.5):")
    return State.ENTER_DO


async def do_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        do_value = float(update.message.text.replace(',', '.'))
        WaterQualityRow.model_validate({'ts': datetime.now(), 'pond_id': 'test', 'dissolved_O2_mgL': do_value, 'temperature_C': 10, 'user': 'test'})
        context.user_data['do'] = do_value
        await update.message.reply_text("✅ DO принято.\n\nТеперь введите температуру, °C (например, 15.2):")
        return State.ENTER_TEMP
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите число (например, 8.5).")
        return State.ENTER_DO


async def temp_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        temp_value = float(update.message.text.replace(',', '.'))
        WaterQualityRow.model_validate({'ts': datetime.now(), 'pond_id': 'test', 'dissolved_O2_mgL': 10, 'temperature_C': temp_value, 'user': 'test'})
        context.user_data['temp'] = temp_value

        summary = (f"Подтвердите данные:\n\n"
                   f"Водоём: {context.user_data['pond'].name}\n"
                   f"DO: {context.user_data['do']} мг/л\n"
                   f"Температура: {temp_value} °C")
        keyboard = [[InlineKeyboardButton("✅ Сохранить", callback_data="confirm_save"), InlineKeyboardButton("❌ Отмена", callback_data="cancel_op")]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return State.CONFIRM_WATER
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите число (например, 15.2).")
        return State.ENTER_TEMP


async def save_water_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        row_data = WaterQualityRow(
            ts=datetime.now(),
            pond_id=context.user_data['pond'].id,
            dissolved_O2_mgL=context.user_data['do'],
            temperature_C=context.user_data['temp'],
            user=f"{context.user_data['current_user'].name} ({context.user_data['current_user'].id})"
        )
        logs.append_water_quality(row_data)
        if row_data.is_critical():
            alert_message = (f"🚨 ВНИМАНИЕ! Критические параметры воды!\n"
                             f"Водоём: {context.user_data['pond'].name}\n"
                             f"DO: {row_data.dissolved_O2_mgL} мг/л\n"
                             f"Температура: {row_data.temperature_C} °C")
            await notify_admins(context, alert_message)
            
            await query.edit_message_text(f"Сохранено! Администраторы уведомлены о крит. параметрах.")
        else:
            await query.edit_message_text("✅ Данные успешно сохранены.")
    except Exception as e:
        log.error(f"Ошибка при сохранении данных о воде: {e}")
        await query.edit_message_text("Произошла ошибка при сохранении.")
    context.user_data.clear()
    return ConversationHandler.END


water_quality_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.WATER_QUALITY), water_quality_start)],
    states={
        State.SELECT_POND_W: [CallbackQueryHandler(pond_selected_for_water, pattern="^pond_")],
        State.ENTER_DO: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_received)],
        State.ENTER_TEMP: [MessageHandler(filters.TEXT & ~filters.COMMAND, temp_received)],
        State.CONFIRM_WATER: [CallbackQueryHandler(save_water_data, pattern="^confirm_save$"), CallbackQueryHandler(cancel, pattern="^cancel_op$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)

# === СЦЕНАРИЙ КОРМЛЕНИЯ ===

@restricted(allowed_roles=[UserRole.OPERATOR, UserRole.ADMIN])
async def feeding_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    if await ask_for_pond_selection(update, "Выберите водоём для кормления:"):
        return State.SELECT_POND_F
    return ConversationHandler.END


async def pond_selected_for_feeding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]

    pond = next((p for p in references.get_active_ponds() if p.id == pond_id), None)
    if not pond:
        await query.edit_message_text("Ошибка: водоём не найден.")
        return ConversationHandler.END
    context.user_data['pond'] = pond

    feed_types = references.get_active_feed_types()
    if not feed_types:
        await query.edit_message_text("В системе нет активных типов кормов. Обратитесь к администратору.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(ft.name, callback_data=f"feed_{ft.id}")] for ft in feed_types]
    await query.edit_message_text(f"Водоём: {pond.name}.\n\nВыберите тип корма:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SELECT_FEED


async def feed_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    query = update.callback_query
    await query.answer()
    feed_id = query.data.split("_")[1]

    feed_type = next((ft for ft in references.get_active_feed_types() if ft.id == feed_id), None)
    if not feed_type:
        await query.edit_message_text("Ошибка: тип корма не найден.")
        return ConversationHandler.END
    context.user_data['feed_type'] = feed_type

    await query.edit_message_text(f"Корм: {feed_type.name}.\n\nВведите массу корма в кг (например, 25.5):")
    return State.ENTER_MASS_F


async def mass_received_feeding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        mass = float(update.message.text.replace(',', '.'))
        FeedingRow.model_validate({'ts': datetime.now(), 'pond_id': 'test', 'feed_type': 'test', 'mass_kg': mass, 'user': 'test'})
        context.user_data['mass'] = mass

        summary = (f"Подтвердите данные:\n\n"
                   f"Водоём: {context.user_data['pond'].name}\n"
                   f"Корм: {context.user_data['feed_type'].name}\n"
                   f"Масса: {mass} кг")
        keyboard = [[InlineKeyboardButton("✅ Сохранить", callback_data="confirm_save"), InlineKeyboardButton("❌ Отмена", callback_data="cancel_op")]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return State.CONFIRM_FEED
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите число.")
        return State.ENTER_MASS_F


async def save_feeding_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        row = FeedingRow(
            ts=datetime.now(),
            pond_id=context.user_data['pond'].id,
            feed_type=context.user_data['feed_type'].name,
            mass_kg=context.user_data['mass'],
            user=f"{context.user_data['current_user'].name} ({context.user_data['current_user'].id})"
        )
        logs.append_feeding(row)
        await query.edit_message_text("✅ Данные о кормлении сохранены.")
    except Exception as e:
        log.error(f"Ошибка сохранения данных о кормлении: {e}")
        await query.edit_message_text("Произошла ошибка при сохранении.")
    context.user_data.clear()
    return ConversationHandler.END


feeding_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.FEEDING), feeding_start)],
    states={
        State.SELECT_POND_F: [CallbackQueryHandler(pond_selected_for_feeding, pattern="^pond_")],
        State.SELECT_FEED: [CallbackQueryHandler(feed_type_selected, pattern="^feed_")],
        State.ENTER_MASS_F: [MessageHandler(filters.TEXT & ~filters.COMMAND, mass_received_feeding)],
        State.CONFIRM_FEED: [CallbackQueryHandler(save_feeding_data, pattern="^confirm_save$"), CallbackQueryHandler(cancel, pattern="^cancel_op$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)

# === КОНТРОЛЬНОЕ ВЗВЕШИВАНИЕ ===

@restricted(allowed_roles=[UserRole.OPERATOR, UserRole.ADMIN])
async def weighing_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    if await ask_for_pond_selection(update, "Выберите водоём для контрольного взвешивания:"):
        return State.SELECT_POND_WGH
    return ConversationHandler.END


async def pond_selected_for_weighing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]
    pond = next((p for p in references.get_active_ponds() if p.id == pond_id), None)
    if not pond:
        await query.edit_message_text("Ошибка: водоём не найден.")
        return ConversationHandler.END
    context.user_data['pond'] = pond
    await query.edit_message_text(f"Водоём: {pond.name}.\n\nВведите средний вес одной рыбы в граммах (например, 350.5):")
    return State.ENTER_WEIGHT


async def weight_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        weight = float(update.message.text.replace(',', '.'))
        WeighingRow.model_validate({'ts': datetime.now(), 'pond_id': 'test', 'avg_weight_g': weight, 'user': 'test'})
        context.user_data['weight'] = weight

        summary = (f"Подтвердите данные:\n\n"
                   f"Водоём: {context.user_data['pond'].name}\n"
                   f"Средний вес: {weight} г")
        keyboard = [[InlineKeyboardButton("✅ Сохранить", callback_data="confirm_save"), InlineKeyboardButton("❌ Отмена", callback_data="cancel_op")]]
        await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
        return State.CONFIRM_WEIGHING

    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите положительное число.")
        return State.ENTER_WEIGHT


async def save_weighing_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        row = WeighingRow(
            ts=datetime.now(),
            pond_id=context.user_data['pond'].id,
            avg_weight_g=context.user_data['weight'],
            user=f"{context.user_data['current_user'].name} ({context.user_data['current_user'].id})"
        )
        logs.append_weighing(row)
        await query.edit_message_text(f"✅ Данные о взвешивании для водоёма '{context.user_data['pond'].name}' сохранены.")
    except Exception as e:
        log.error(f"Ошибка сохранения данных о взвешивании: {e}")
        await query.edit_message_text("Произошла ошибка при сохранении.")

    context.user_data.clear()
    return ConversationHandler.END


weighing_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.WEIGHING), weighing_start)],
    states={
        State.SELECT_POND_WGH: [CallbackQueryHandler(pond_selected_for_weighing, pattern="^pond_")],
        State.ENTER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, weight_received)],
        State.CONFIRM_WEIGHING: [
            CallbackQueryHandler(save_weighing_data, pattern="^confirm_save$"),
            CallbackQueryHandler(cancel, pattern="^cancel_op$")
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)

# === СЦЕНАРИЙ: ДВИЖЕНИЕ РЫБЫ ===

@restricted(allowed_roles=[UserRole.OPERATOR, UserRole.ADMIN])
async def fish_move_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    # Шаг 1: Выбор ИСХОДНОГО водоёма
    if await ask_for_pond_selection(update, "Выберите ИСХОДНЫЙ водоём для регистрации движения рыбы:"):
        return State.SELECT_POND_FM_SRC
    return ConversationHandler.END


async def pond_src_selected_for_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    # Шаг 2: Выбор типа операции
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]
    pond = next((p for p in references.get_active_ponds() if p.id == pond_id), None)
    if not pond:
        await query.edit_message_text("Ошибка: водоём не найден.")
        return ConversationHandler.END
    context.user_data['pond_src'] = pond  # Сохраняем как исходный

    keyboard = [
        [InlineKeyboardButton("🐟 Зарыбление", callback_data=f"move_{FishMoveType.STOCKING.value}")],
        [InlineKeyboardButton("💰 Продажа", callback_data=f"move_{FishMoveType.SALE.value}")],
        [InlineKeyboardButton("☠️ Гибель", callback_data=f"move_{FishMoveType.DEATH.value}")],
        [InlineKeyboardButton("➡️ Перевод в другой водоём", callback_data="move_transfer")]
    ]
    await query.edit_message_text(f"Водоём-источник: {pond.name}.\n\nВыберите тип операции:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SELECT_MOVE_TYPE


async def move_type_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    # Шаг 3: Если перевод - выбор водоёма-получателя, иначе - ввод количества
    query = update.callback_query
    await query.answer()

    # Если это не перевод
    if query.data != "move_transfer":
        move_type = FishMoveType(query.data.split("_")[1])
        context.user_data['move_type'] = move_type
        # Для зарыбления не нужен водоем-источник, он и есть получатель
        if move_type == FishMoveType.STOCKING:
            context.user_data['pond_dest'] = context.user_data['pond_src']
            del context.user_data['pond_src']
            await query.edit_message_text(f"Операция: Зарыбление.\nВодоём: {context.user_data['pond_dest'].name}\n\nВведите количество рыбы (шт):")
        else:
            await query.edit_message_text(f"Тип операции: {move_type.value}.\n\nВведите количество рыбы (шт):")
        return State.ENTER_QUANTITY_FM

    # Если это перевод - запрашиваем водоём-получатель
    context.user_data['move_type'] = 'transfer'  # специальный флаг
    pond_src = context.user_data['pond_src']

    # Получаем все активные водоемы, кроме исходного
    other_ponds = [p for p in references.get_active_ponds() if p.id != pond_src.id]

    if not other_ponds:
        await query.edit_message_text("Нет других активных водоёмов для перевода. Операция отменена.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(p.name, callback_data=f"ponddest_{p.id}")] for p in other_ponds]
    await query.edit_message_text("Выберите водоём-ПОЛУЧАТЕЛЬ:", reply_markup=InlineKeyboardMarkup(keyboard))
    return State.SELECT_POND_FM_DEST


async def pond_dest_selected_for_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    # Шаг 3.1: Получили водоем-получатель, теперь запрашиваем количество
    query = update.callback_query
    await query.answer()
    pond_id = query.data.split("_")[1]
    pond_dest = next((p for p in references.get_active_ponds() if p.id == pond_id), None)
    if not pond_dest:
        await query.edit_message_text("Ошибка: водоём-получатель не найден.")
        return ConversationHandler.END
    context.user_data['pond_dest'] = pond_dest

    pond_src = context.user_data['pond_src']
    await query.edit_message_text(
        f"Перевод из '{pond_src.name}' в '{pond_dest.name}'.\n\n"
        "Введите количество рыбы для перевода (шт):"
    )
    return State.ENTER_QUANTITY_FM


async def quantity_received_fm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        quantity = int(update.message.text)
        if quantity <= 0: raise ValueError
        context.user_data['quantity'] = quantity
        await update.message.reply_text("Введите средний вес одной рыбы в граммах (не обязательно, можно 0):")
        return State.ENTER_AVG_WEIGHT_FM
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите целое положительное число.")
        return State.ENTER_QUANTITY_FM


async def avg_weight_received_fm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    try:
        weight = float(update.message.text.replace(',', '.'))
        if weight < 0: raise ValueError
        context.user_data['avg_weight_g'] = weight if weight > 0 else None
        await update.message.reply_text("Введите причину или комментарий (например, 'Плановый перевод'):")
        return State.ENTER_REASON_FM
    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите положительное число.")
        return State.ENTER_AVG_WEIGHT_FM


async def reason_received_fm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    context.user_data['reason'] = update.message.text
    await update.message.reply_text("Введите ссылку на документ/заказ (например, 'Акт #25'). Можно пропустить, написав 'нет':")
    return State.ENTER_REF_FM


async def ref_received_fm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> State:
    ref_value = update.message.text
    context.user_data['ref'] = ref_value if ref_value.lower() != 'нет' else None

    # Собираем данные для подтверждения
    move_type = context.user_data['move_type']
    quantity = context.user_data['quantity']
    avg_weight = context.user_data.get('avg_weight_g')
    reason = context.user_data['reason']
    ref = context.user_data.get('ref')

    summary = "<b>Подтвердите данные:</b>\n\n"
    if move_type == 'transfer':
        pond_src = context.user_data['pond_src']
        pond_dest = context.user_data['pond_dest']
        summary += (
            f"<b>Операция:</b> Перевод\n"
            f"<b>Из:</b> {pond_src.name}\n"
            f"<b>В:</b> {pond_dest.name}\n"
        )
    else:  # sale, death, stocking
        pond = context.user_data.get('pond_src') or context.user_data.get('pond_dest')
        summary += (
            f"<b>Операция:</b> {move_type.value}\n"
            f"<b>Водоём:</b> {pond.name}\n"
        )

    summary += (
        f"<b>Количество:</b> {quantity} шт.\n"
        f"<b>Средний вес:</b> {avg_weight or 'не указан'} г\n"
        f"<b>Причина:</b> {reason}\n"
        f"<b>Ссылка (ref):</b> {ref or 'нет'}"
    )
    keyboard = [[InlineKeyboardButton("✅ Сохранить", callback_data="confirm_save"), InlineKeyboardButton("❌ Отмена", callback_data="cancel_op")]]
    await update.message.reply_text(summary, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return State.CONFIRM_FISH_MOVE


async def save_fish_move_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    try:
        user_str = f"{context.user_data['current_user'].name} ({context.user_data['current_user'].id})"
        common_data = {
            'ts': datetime.now(),
            'quantity': context.user_data['quantity'],
            'avg_weight_g': context.user_data.get('avg_weight_g'),
            'reason': context.user_data.get('reason', ''),
            'ref': context.user_data.get('ref'),
            'user': user_str
        }

        # Если это перевод, создаем ДВЕ записи
        if context.user_data['move_type'] == 'transfer':
            pond_src = context.user_data['pond_src']
            pond_dest = context.user_data['pond_dest']

            # Запись о расходе из исходного водоема
            row_out = FishMoveRow(
                pond_id=pond_src.id,
                move_type=FishMoveType.TRANSFER_OUT,
                **common_data
            )
            # Запись о приходе в водоем-получатель
            row_in = FishMoveRow(
                pond_id=pond_dest.id,
                move_type=FishMoveType.TRANSFER_IN,
                **common_data
            )
            logs.append_fish_move(row_out)
            logs.append_fish_move(row_in)
            await query.edit_message_text(f"✅ Перевод {common_data['quantity']} шт. из '{pond_src.name}' в '{pond_dest.name}' успешно зарегистрирован.")

        else:  # Иначе создаем одну запись
            move_type = context.user_data['move_type']
            pond = context.user_data.get('pond_src') or context.user_data.get('pond_dest')
            row = FishMoveRow(
                pond_id=pond.id,
                move_type=move_type,
                **common_data
            )
            logs.append_fish_move(row)
            await query.edit_message_text(f"✅ Операция '{move_type.value}' для водоёма '{pond.name}' успешно сохранена.")

    except Exception as e:
        log.error(f"Ошибка сохранения данных о движении рыбы: {e}")
        await query.edit_message_text(f"Произошла ошибка при сохранении: {e}")
    context.user_data.clear()
    return ConversationHandler.END


fish_move_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.FISH_MOVE), fish_move_start)],
    states={
        State.SELECT_POND_FM_SRC: [CallbackQueryHandler(pond_src_selected_for_move, pattern="^pond_")],
        State.SELECT_MOVE_TYPE: [CallbackQueryHandler(move_type_selected, pattern="^move_")],
        State.SELECT_POND_FM_DEST: [CallbackQueryHandler(pond_dest_selected_for_move, pattern="^ponddest_")],
        State.ENTER_QUANTITY_FM: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_received_fm)],
        State.ENTER_AVG_WEIGHT_FM: [MessageHandler(filters.TEXT & ~filters.COMMAND, avg_weight_received_fm)],
        State.ENTER_REASON_FM: [MessageHandler(filters.TEXT & ~filters.COMMAND, reason_received_fm)],
        State.ENTER_REF_FM: [MessageHandler(filters.TEXT & ~filters.COMMAND, ref_received_fm)],
        State.CONFIRM_FISH_MOVE: [CallbackQueryHandler(save_fish_move_data, pattern="^confirm_save$"), CallbackQueryHandler(cancel, pattern="^cancel_op$")],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)