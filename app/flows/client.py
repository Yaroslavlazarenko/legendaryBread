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
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.models.product import Product
from app.sheets import references, logs
from app.bot.notifications import notify_admins
from app.utils.logger import log
from .common import cancel

class OrderState(Enum):
    SELECT_PRODUCT = auto()
    ENTER_QUANTITY = auto()
    CHECKOUT_OR_ADD = auto()

@restricted(allowed_roles=[UserRole.CLIENT, UserRole.ADMIN])
async def catalog_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отображает статичный каталог товаров."""
    products = references.get_available_products()
    if not products:
        await update.message.reply_text("Извините, в данный момент доступных товаров нет.")
        return

    message = "<b>Наш Каталог:</b>\n\n"
    for p in products:
        message += f"🔹 <b>{p.name}</b>\n"
        message += f"   <i>{p.description}</i>\n"
        message += f"   Цена: {p.get_display_price()}\n\n"
    
    await update.message.reply_text(message, parse_mode='HTML')
    await update.message.reply_text("Для оформления заказа используйте команду /order")

@restricted(allowed_roles=[UserRole.CLIENT, UserRole.ADMIN])
async def order_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> OrderState | int:
    """Начинает или продолжает процесс заказа."""
    context.user_data['cart'] = context.user_data.get('cart', {})
    
    products = references.get_available_products()
    if not products:
        if update.callback_query:
             await update.callback_query.edit_message_text("К сожалению, сейчас нет доступных товаров для заказа.")
        else:
            await update.message.reply_text("К сожалению, сейчас нет доступных товаров для заказа.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(f"{p.name} ({p.get_display_price()})", callback_data=f"prod_{p.id}") for p in products]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Выберите товар для добавления в корзину:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)
        
    return OrderState.SELECT_PRODUCT

async def product_selected_for_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> OrderState:
    """Обрабатывает выбор товара и запрашивает количество."""
    query = update.callback_query
    await query.answer()
    product_id_from_callback = query.data.split("_")[1]
    
    product = next((p for p in references.get_available_products() if p.id == product_id_from_callback), None)
    if not product:
        await query.edit_message_text("Этот товар больше не доступен. Пожалуйста, выберите другой.")
        return await order_start(update, context)

    context.user_data['selected_product'] = product
    await query.edit_message_text(f"Выбран товар: {product.name}.\n\nВведите желаемое количество (в {product.unit}):")
    return OrderState.ENTER_QUANTITY

async def quantity_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> OrderState:
    """Обрабатывает введенное количество и добавляет товар в корзину."""
    try:
        quantity_str = update.message.text.replace(',', '.')
        quantity = float(quantity_str)
        if quantity <= 0:
            raise ValueError("Количество должно быть положительным.")
        
        product = context.user_data['selected_product']
        cart = context.user_data.get('cart', {})
        
        cart[product.id] = {'product': product.model_dump(by_alias=True), 'quantity': quantity}
        context.user_data['cart'] = cart
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить еще товар", callback_data="add_more")],
            [InlineKeyboardButton("🛒 Оформить заказ", callback_data="checkout")],
        ]
        await update.message.reply_text(
            f"✅ {product.name} ({quantity} {product.unit}) добавлен в корзину.", 
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return OrderState.CHECKOUT_OR_ADD

    except (ValueError, TypeError):
        await update.message.reply_text("❗️Неверный формат. Введите положительное число (например, 1.5 или 10).")
        return OrderState.ENTER_QUANTITY

async def show_cart_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> OrderState | int:
    """Показывает содержимое корзины и запрашивает подтверждение заказа."""
    query = update.callback_query
    await query.answer()
    
    cart = context.user_data.get('cart', {})
    if not cart:
        await query.edit_message_text("Ваша корзина пуста. Чтобы начать, используйте /order")
        return ConversationHandler.END

    user = context.user_data['current_user']
    order_id = f"ORD-{int(datetime.now().timestamp())}-{user.id}"
    context.user_data['order_id'] = order_id
    
    message = "<b>🛒 Ваш заказ:</b>\n\n"
    total_amount = 0
    
    for item_data in cart.values():
        product = Product.model_validate(item_data['product'])
        quantity = item_data['quantity']
        item_total = product.price * quantity
        total_amount += item_total
        message += f" • {product.name}: {quantity} {product.unit} x {product.price:.2f} грн = {item_total:.2f} грн\n"

    message += f"\n<b>Итого к оплате: {total_amount:.2f} грн</b>\n\n"
    message += f"Ваш контактный телефон для связи: {user.phone}\n\n"
    message += "Подтверждаете заказ?"
    context.user_data['total_amount'] = total_amount

    keyboard = [[
        InlineKeyboardButton("✅ Да, подтвердить", callback_data="confirm_order"),
        InlineKeyboardButton("❌ Отмена", callback_data="cancel_order"),
    ]]
    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
    return OrderState.CHECKOUT_OR_ADD

async def finalize_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Сохраняет заказ в Google Sheets и уведомляет администратора."""
    query = update.callback_query
    await query.answer()
    try:
        user = context.user_data['current_user']
        cart = context.user_data['cart']
        order_id = context.user_data['order_id']
        total_amount = context.user_data['total_amount']

        # ИСПРАВЛЕНИЕ 1: Используем 'id' вместо 'order_id'
        order_row = SalesOrderRow(
            order_id=order_id,
            ts=datetime.now(),
            client_id=user.id,
            client_name=user.name,
            phone=user.phone or "-",
            status="new", 
            total_amount=total_amount
        )
        logs.append_sales_order(order_row)
        
        admin_order_details = ""
        # ИСПРАВЛЕНИЕ 2 (улучшение надежности)
        for item_data in cart.values():
            product_obj = Product.model_validate(item_data['product'])
            
            item_row = SalesOrderItemRow(
                order_id=order_id, 
                product_id=product_obj.id, 
                product_name=product_obj.name,
                quantity=item_data['quantity'], 
                price_per_unit=product_obj.price
            )
            logs.append_sales_order_item(item_row)
            admin_order_details += f" • {item_row.product_name}: {item_row.quantity} {product_obj.unit}\n"

        references.get_all_orders.cache_clear()
        references.get_all_order_items.cache_clear()

        await query.edit_message_text(f"✅ Ваш заказ #{order_id.split('-')[1]} принят! Спасибо, мы скоро с вами свяжемся.")

        admin_message = (
            f"📦 <b>Новый заказ #{order_id.split('-')[1]}</b>\n\n"
            f"<b>Клиент:</b> {user.name}\n<b>Телефон:</b> {user.phone}\n\n"
            f"<b>Состав заказа:</b>\n{admin_order_details}\n"
            f"<b>Сумма: {total_amount:.2f} грн</b>"
        )
        await notify_admins(context, admin_message, parse_mode='HTML')
        
    except Exception as e:
        log.error(f"Ошибка при оформлении заказа {order_id}: {e}")
        await query.edit_message_text("К сожалению, произошла ошибка. Заказ не был оформлен. Пожалуйста, попробуйте еще раз.")
    
    for key in ['cart', 'selected_product', 'order_id', 'total_amount']:
        if key in context.user_data:
            del context.user_data[key]
            
    return ConversationHandler.END

client_order_conv_handler = ConversationHandler(
    entry_points=[MessageHandler(filters.Text(ReplyButton.MAKE_ORDER), order_start)],
    states={
        OrderState.SELECT_PRODUCT: [CallbackQueryHandler(product_selected_for_order, pattern="^prod_")],
        OrderState.ENTER_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity_received)],
        OrderState.CHECKOUT_OR_ADD: [
            CallbackQueryHandler(order_start, pattern="^add_more$"),
            CallbackQueryHandler(show_cart_and_confirm, pattern="^checkout$"),
            CallbackQueryHandler(finalize_order, pattern="^confirm_order$"),
            CallbackQueryHandler(cancel, pattern="^cancel_order$"),
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    allow_reentry=True
)