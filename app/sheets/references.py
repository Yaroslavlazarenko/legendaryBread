# app/sheets/references.py

from cachetools import cached, TTLCache
from datetime import date, datetime # Добавлен импорт datetime для отладки
from app.sheets.client import gs_client
from app.models.user import User, UserRole
from app.models.pond import Pond
from app.models.feeding import FeedType
from app.models.product import Product
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.config.settings import settings
from app.utils.logger import log

# --- КОНСТАНТЫ ДЛЯ МАППИНГА КОЛОНОК ---
USER_COLUMN_MAP = {'role': 4, 'notifications_enabled': 5}
POND_COLUMN_MAP = {'name': 2, 'type': 3, 'species': 4, 'stocking_date': 5, 'initial_qty': 6, 'notes': 7, 'is_active': 8}
FEED_TYPE_COLUMN_MAP = {'name': 2, 'is_active': 3}
PRODUCT_COLUMN_MAP = {'name': 2, 'description': 3, 'price': 4, 'unit': 5, 'is_available': 6}
ORDER_COLUMN_MAP = {'status': 6} # Added for consistency

# --- РАЗДЕЛЕННЫЕ КЭШИ ---
user_cache = TTLCache(maxsize=10, ttl=60)
pond_cache = TTLCache(maxsize=10, ttl=60)
feed_type_cache = TTLCache(maxsize=10, ttl=60)
product_cache = TTLCache(maxsize=10, ttl=60)
order_cache = TTLCache(maxsize=10, ttl=60)
order_item_cache = TTLCache(maxsize=10, ttl=60)


# --- USERS ---
@cached(user_cache) # Используем user_cache
def get_all_users() -> list[User]:
    users_data = gs_client.get_sheet_data(settings.SHEETS.USERS)
    return [User.model_validate(row) for row in users_data]

def get_user_by_id(user_id: int) -> User | None:
    for user in get_all_users():
        if user.id == user_id:
            return user
    return None

def update_user_role(user_id: int, new_role: UserRole) -> bool:
    user_cache.clear() # Clear specific cache after update
    return gs_client.update_cell_by_match(settings.SHEETS.USERS, 1, user_id, USER_COLUMN_MAP['role'], new_role.value)

def get_admins() -> list[User]:
    """Возвращает список всех администраторов с активными уведомлениями."""
    return [u for u in get_all_users() if u.role == UserRole.ADMIN and u.notifications_enabled]

# --- PONDS ---
@cached(pond_cache) # Используем pond_cache
def get_all_ponds() -> list[Pond]:
    ponds_data = gs_client.get_sheet_data(settings.SHEETS.PONDS)
    parsed_ponds = []
    for row in ponds_data:
        # Handle empty but existing date strings
        if 'stocking_date' in row and row['stocking_date']:
            try:
                # Assuming date is in ISO format YYYY-MM-DD
                row['stocking_date'] = date.fromisoformat(row['stocking_date'])
            except (ValueError, TypeError):
                row['stocking_date'] = None
        else:
            row['stocking_date'] = None
        
        # Handle empty initial quantity
        if 'initial_qty' in row and row['initial_qty'] == '':
            row['initial_qty'] = None

        parsed_ponds.append(Pond.model_validate(row))
    return parsed_ponds

def get_pond_by_id(pond_id: str) -> Pond | None:
    for pond in get_all_ponds():
        if pond.id == pond_id:
            return pond
    return None

def get_active_ponds() -> list[Pond]:
    return [p for p in get_all_ponds() if p.is_active]

def update_pond_status(pond_id: str, is_active: bool) -> bool:
    pond_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.PONDS, 1, pond_id, POND_COLUMN_MAP['is_active'], str(is_active).upper())

def update_pond_details(pond_id: str, field_name: str, new_value: any) -> bool:
    col_index = POND_COLUMN_MAP.get(field_name)
    if not col_index:
        log.error(f"Неизвестное поле '{field_name}' для обновления в листе PONDS.")
        return False
    pond_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.PONDS, 1, pond_id, col_index, new_value)

# --- FEED TYPES ---
@cached(feed_type_cache) # Используем feed_type_cache
def get_feed_types() -> list[FeedType]:
    feed_data = gs_client.get_sheet_data(settings.SHEETS.FEED_TYPES)
    return [FeedType.model_validate(row) for row in feed_data]

def get_feed_type_by_id(feed_id: str) -> FeedType | None:
    for feed_type in get_feed_types():
        if feed_type.id == feed_id:
            return feed_type
    return None

def get_active_feed_types() -> list[FeedType]:
    return [ft for ft in get_feed_types() if ft.is_active]

def update_feed_type_status(feed_id: str, is_active: bool) -> bool:
    feed_type_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.FEED_TYPES, 1, feed_id, FEED_TYPE_COLUMN_MAP['is_active'], str(is_active).upper())

def update_feed_type_details(feed_id: str, field_name: str, new_value: str) -> bool:
    col_index = FEED_TYPE_COLUMN_MAP.get(field_name)
    if not col_index:
        log.error(f"Неизвестное поле '{field_name}' для обновления в листе FEED_TYPES.")
        return False
    feed_type_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.FEED_TYPES, 1, feed_id, col_index, new_value)

# --- PRODUCTS ---
@cached(product_cache) # Используем product_cache
def get_all_products() -> list[Product]:
    products_data = gs_client.get_sheet_data(settings.SHEETS.PRODUCTS)
    return [Product.model_validate(row) for row in products_data]

def get_product_by_id(product_id: str) -> Product | None:
    for product in get_all_products():
        if product.id == product_id:
            return product
    return None

def get_available_products() -> list[Product]:
    return [p for p in get_all_products() if p.is_available]

def update_product_status(product_id: str, is_available: bool) -> bool:
    product_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.PRODUCTS, 1, product_id, PRODUCT_COLUMN_MAP['is_available'], str(is_available).upper())

def update_product_details(product_id: str, field_name: str, new_value: any) -> bool:
    col_index = PRODUCT_COLUMN_MAP.get(field_name)
    if not col_index:
        log.error(f"Неизвестное поле '{field_name}' для обновления в листе PRODUCTS.")
        return False
    product_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.PRODUCTS, 1, product_id, col_index, new_value)

# --- ORDERS ---
@cached(order_cache) # Используем order_cache
def get_all_orders() -> list[SalesOrderRow]:
    """Возвращает список всех заказов из листа."""
    orders_data = gs_client.get_sheet_data(settings.SHEETS.SALES_ORDERS)
    return [SalesOrderRow.model_validate(row) for row in orders_data]

def get_orders_by_status(status: str) -> list[SalesOrderRow]:
    return [order for order in get_all_orders() if order.status == status]

@cached(order_item_cache) # Используем order_item_cache
def get_all_order_items() -> list[SalesOrderItemRow]:
    items_data = gs_client.get_sheet_data(settings.SHEETS.SALES_ORDER_ITEMS)
    return [SalesOrderItemRow.model_validate(row) for row in items_data]

def get_order_items(order_id: str) -> list[SalesOrderItemRow]:
    # FIX: Access the attribute by its correct Python name, 'order_id'
    return [item for item in get_all_order_items() if item.order_id == order_id]

def update_order_status(order_id: str, new_status: str) -> bool:
    order_cache.clear() # Clear specific cache
    return gs_client.update_cell_by_match(settings.SHEETS.SALES_ORDERS, 1, order_id, ORDER_COLUMN_MAP['status'], new_status)

def update_user_notification_status(user_id: int, status: bool) -> bool:
    """Обновляет статус уведомлений для пользователя."""
    user_cache.clear() # Очищаем кэш после обновления
    # В таблице булево значение должно быть строкой 'TRUE' или 'FALSE'
    status_str = str(status).upper()
    return gs_client.update_cell_by_match(
        settings.SHEETS.USERS, 1, user_id, USER_COLUMN_MAP['notifications_enabled'], status_str
    )