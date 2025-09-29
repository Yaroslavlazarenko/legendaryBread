from math import ceil
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from app.models.user import UserRole # <-- Добавьте импорт

# --- КОНСТАНТЫ ДЛЯ ТЕКСТА КНОПОК ГЛАВНОГО МЕНЮ ---
class ReplyButton:
    # Admin
    ADMIN_PANEL = "👑 Панель администратора"
    MANAGE_PRODUCTS = "🛒 Управление товарами"
    MANAGE_PONDS = "🏞️ Управление водоёмами"
    MANAGE_FEED_TYPES = "🥫 Управление типами кормов"
    SETTINGS = "⚙️ Настройки"
    
    # Operator & Admin
    STOCK_CONTROL = "📦 Учет склада кормов"
    WATER_QUALITY = "💧 Замер воды"
    FEEDING = "🍲 Кормление"
    WEIGHING = "⚖️ Взвешивание"
    FISH_MOVE = "🐟 Движение рыбы"

    # Client & Admin
    CATALOG = "🛍️ Каталог"
    MAKE_ORDER = "📝 Сделать заказ"


def create_main_menu_keyboard(role: UserRole) -> ReplyKeyboardMarkup:
    """Создает ReplyKeyboardMarkup с кнопками главного меню в зависимости от роли."""
    keyboard = []

    if role == UserRole.ADMIN:
        keyboard.extend([
            [KeyboardButton(ReplyButton.ADMIN_PANEL)],
            [KeyboardButton(ReplyButton.MANAGE_PRODUCTS), KeyboardButton(ReplyButton.MANAGE_PONDS)],
            [KeyboardButton(ReplyButton.MANAGE_FEED_TYPES), KeyboardButton(ReplyButton.STOCK_CONTROL)],
            [KeyboardButton(ReplyButton.SETTINGS)],
        ])
    
    if role in [UserRole.ADMIN, UserRole.OPERATOR]:
        # Добавляем разделитель для наглядности, если это админ
        if role == UserRole.ADMIN:
            keyboard.append([KeyboardButton("--- 🛠️ Оператор ---")]) # Просто текстовая кнопка
            
        keyboard.extend([
            [KeyboardButton(ReplyButton.WATER_QUALITY), KeyboardButton(ReplyButton.FEEDING)],
            [KeyboardButton(ReplyButton.WEIGHING), KeyboardButton(ReplyButton.FISH_MOVE)],
        ])
        # Для оператора кнопка склада будет здесь
        if role == UserRole.OPERATOR:
            keyboard.append([KeyboardButton(ReplyButton.STOCK_CONTROL)])

    if role in [UserRole.ADMIN, UserRole.CLIENT]:
        if role == UserRole.ADMIN:
            keyboard.append([KeyboardButton("--- 👨‍💼 Клиент ---")])
        
        keyboard.extend([
            [KeyboardButton(ReplyButton.CATALOG), KeyboardButton(ReplyButton.MAKE_ORDER)],
        ])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def create_paginated_keyboard(
    items: list,
    page: int = 0,
    page_size: int = 5,
    button_text_formatter: callable = lambda item: str(item),
    button_callback_formatter: callable = lambda item: f"item_{item.id}",
    pagination_callback_prefix: str = "page_",
    extra_buttons: list[list[InlineKeyboardButton]] | None = None
) -> InlineKeyboardMarkup:
    """
    Создает универсальную Inline-клавиатуру с пагинацией.
    (Этот код остается без изменений)
    """
    # ... (существующий код функции)
    if not items:
        keyboard = extra_buttons or []
        return InlineKeyboardMarkup(keyboard)

    total_pages = ceil(len(items) / page_size)
    page = max(0, min(page, total_pages - 1)) # Убедимся, что страница в допустимых границах

    start_index = page * page_size
    end_index = start_index + page_size
    page_items = items[start_index:end_index]

    keyboard = [
        [InlineKeyboardButton(
            button_text_formatter(item),
            callback_data=button_callback_formatter(item)
        )] for item in page_items
    ]

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{pagination_callback_prefix}{page - 1}"))
    
    if total_pages > 1:
        nav_buttons.append(InlineKeyboardButton(f"📄 {page + 1}/{total_pages}", callback_data="noop")) # noop - no operation

    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"{pagination_callback_prefix}{page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)

    if extra_buttons:
        keyboard.extend(extra_buttons)

    return InlineKeyboardMarkup(keyboard)