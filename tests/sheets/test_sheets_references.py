import pytest
from unittest.mock import patch, MagicMock

from app.sheets import references
from app.models.user import User, UserRole
from app.models.pond import Pond
from app.models.product import Product
from app.models.feeding import FeedType
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.config.settings import settings


@pytest.fixture
def mock_gs_client():
    """Фикстура для мокинга gs_client."""
    # FIX 1: Patch gs_client where it is USED
    with patch('app.sheets.references.gs_client', autospec=True) as mock_client:
        yield mock_client

@pytest.fixture(autouse=True)
def clear_lru_cache():
    """Clears all lru_cache instances in the references module before each test."""
    functions_with_cache = [
        references.get_user_by_id,
        references.get_all_users,
        references.get_pond_by_id,
        references.get_active_ponds,
        references.get_all_ponds, # <--- ADDED THIS LINE
        references.get_active_feed_types,
        references.get_available_products,
        references.get_orders_by_status,
        references.get_order_items
    ]
    for func in functions_with_cache:
        # Check if the function has a cache_clear method before calling it
        if hasattr(func, 'cache_clear'):
            func.cache_clear()
    yield

# --- USERS ---

def test_get_user_by_id_found(mock_gs_client: MagicMock):
    """Тест: get_user_by_id находит существующего пользователя."""
    mock_users_data = [
        {'user_id': 1, 'user_name': 'Admin User', 'phone_number': '111', 'role': 'admin'},
        {'user_id': 2, 'user_name': 'Test User', 'phone_number': '222', 'role': 'client'},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_users_data
    user = references.get_user_by_id(2)
    assert user is not None
    assert isinstance(user, User)
    assert user.id == 2

def test_get_user_by_id_not_found(mock_gs_client: MagicMock):
    """Тест: get_user_by_id возвращает None, если пользователь не найден."""
    mock_gs_client.get_sheet_data.return_value = []
    user = references.get_user_by_id(999)
    assert user is None

def test_get_all_users(mock_gs_client: MagicMock):
    """Тест: get_all_users возвращает список всех пользователей."""
    mock_users_data = [
        {'user_id': 1, 'user_name': 'Admin', 'role': 'admin'},
        {'user_id': 2, 'user_name': 'Client', 'role': 'client'},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_users_data
    users = references.get_all_users()
    assert len(users) == 2
    assert all(isinstance(u, User) for u in users)

def test_update_user_role(mock_gs_client: MagicMock):
    """Тест: update_user_role вызывает метод клиента с правильными параметрами."""
    references.update_user_role(123, UserRole.OPERATOR)
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.USERS, 1, 123, 4, UserRole.OPERATOR.value
    )

# --- PONDS ---

def test_get_pond_by_id_found(mock_gs_client: MagicMock):
    """Тест: get_pond_by_id находит существующий водоём."""
    # This data will be cached by get_all_ponds if not cleared.
    mock_ponds_data = [{'pond_id': 'P1', 'name': 'Pond One', 'is_active': True}] 
    mock_gs_client.get_sheet_data.return_value = mock_ponds_data
    pond = references.get_pond_by_id('P1')
    assert pond is not None
    assert pond.id == 'P1'

def test_get_active_ponds(mock_gs_client: MagicMock):
    """Тест: get_active_ponds возвращает только активные водоёмы."""
    mock_ponds_data = [
        {'pond_id': 'P1', 'name': 'Active', 'is_active': True},
        {'pond_id': 'P2', 'name': 'Inactive', 'is_active': False},
        {'pond_id': 'P3', 'name': 'Active Str', 'is_active': 'TRUE'}, # Pydantic converts 'TRUE' to True
    ]
    mock_gs_client.get_sheet_data.return_value = mock_ponds_data
    active_ponds = references.get_active_ponds()
    assert len(active_ponds) == 2
    assert active_ponds[0].id == 'P1'
    assert active_ponds[1].id == 'P3'
    # Also verify names are correct after fixing cache
    assert active_ponds[0].name == 'Active'
    assert active_ponds[1].name == 'Active Str'


def test_update_pond_status(mock_gs_client: MagicMock):
    """Тест: update_pond_status вызывает метод клиента с правильными параметрами."""
    references.update_pond_status("P1", False)
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.PONDS, 1, "P1", 8, "FALSE"
    )

def test_update_pond_details(mock_gs_client: MagicMock):
    """Тест: update_pond_details вызывает метод клиента с правильными параметрами."""
    references.update_pond_details("P1", "name", "New Name")
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.PONDS, 1, "P1", 2, "New Name"
    )

# --- FEED TYPES ---

def test_get_active_feed_types(mock_gs_client: MagicMock):
    """Тест: get_active_feed_types возвращает только активные типы корма."""
    mock_feed_data = [
        {'feed_id': 'F1', 'name': 'Active', 'is_active': True},
        {'feed_id': 'F2', 'name': 'Inactive', 'is_active': False},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_feed_data
    active_feeds = references.get_active_feed_types()
    assert len(active_feeds) == 1
    assert active_feeds[0].id == 'F1'

def test_update_feed_type_details(mock_gs_client: MagicMock):
    """Тест: update_feed_type_details вызывает метод клиента."""
    references.update_feed_type_details("F1", "name", "New Feed Name")
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.FEED_TYPES, 1, "F1", 2, "New Feed Name"
    )

# --- PRODUCTS ---

    
def test_get_available_products(mock_gs_client: MagicMock):
    """Тест: get_available_products возвращает только доступные товары."""
    # FIX: Add the required 'description' field to the mock data.
    mock_products_data = [
        {'product_id': 'P1', 'name': 'Available', 'description': 'Fresh fish', 'price': 100, 'unit': 'kg', 'is_available': True},
        {'product_id': 'P2', 'name': 'Unavailable', 'description': 'Not available', 'price': 100, 'unit': 'kg', 'is_available': False},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_products_data
    products = references.get_available_products()
    assert len(products) == 1
    assert products[0].id == 'P1'

def test_update_product_details(mock_gs_client: MagicMock):
    """Тест: update_product_details вызывает метод клиента."""
    references.update_product_details("P1", "price", 150.5)
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.PRODUCTS, 1, "P1", 4, 150.5
    )

# --- ORDERS ---

def test_get_orders_by_status(mock_gs_client: MagicMock):
    """Тест: get_orders_by_status фильтрует заказы по статусу."""
    # FIX 2: Provide complete data to satisfy the Pydantic model
    mock_orders_data = [
        {'order_id': 'O1', 'status': 'new', 'client_id': 1, 'ts': '2023-01-01T12:00:00', 'client_name': 'A', 'phone': '111', 'total_amount': 100},
        {'order_id': 'O2', 'status': 'confirmed', 'client_id': 2, 'ts': '2023-01-01T12:00:00', 'client_name': 'B', 'phone': '222', 'total_amount': 200},
        {'order_id': 'O3', 'status': 'new', 'client_id': 3, 'ts': '2023-01-01T12:00:00', 'client_name': 'C', 'phone': '333', 'total_amount': 300},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_orders_data
    new_orders = references.get_orders_by_status('new')
    assert len(new_orders) == 2
    assert all(isinstance(o, SalesOrderRow) for o in new_orders)
    assert new_orders[0].id == 'O1'

def test_get_order_items(mock_gs_client: MagicMock):
    """Тест: get_order_items получает все позиции для одного заказа."""
    # Add extra fields to satisfy the model
    mock_items_data = [
        {'order_id': 'O1', 'product_id': 'P1', 'product_name': 'Fish A', 'quantity': 1, 'price_per_unit': 10},
        {'order_id': 'O2', 'product_id': 'P2', 'product_name': 'Fish B', 'quantity': 2, 'price_per_unit': 20},
        {'order_id': 'O1', 'product_id': 'P3', 'product_name': 'Fish C', 'quantity': 3, 'price_per_unit': 30},
    ]
    mock_gs_client.get_sheet_data.return_value = mock_items_data
    order_items = references.get_order_items('O1')
    assert len(order_items) == 2
    assert all(isinstance(i, SalesOrderItemRow) for i in order_items)
    
def test_update_order_status(mock_gs_client: MagicMock):
    """Тест: update_order_status вызывает метод клиента."""
    references.update_order_status("O1", "confirmed")
    mock_gs_client.update_cell_by_match.assert_called_once_with(
        settings.SHEETS.SALES_ORDERS, 1, "O1", 6, "confirmed"
    )