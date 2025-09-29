import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from app.sheets import logs
from app.config.settings import settings
from app.models.user import User, UserRole
from app.models.pond import Pond
from app.models.product import Product
from app.models.feeding import FeedingRow, FeedType
from app.models.water import WaterQualityRow
from app.models.stock import StockMoveRow, StockMoveType
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.models.weighing import WeighingRow
from app.models.fish import FishMoveRow, FishMoveType


@pytest.fixture
def mock_gs_client():
    """Фикстура для мокинга gs_client."""
    # FIX 2: Patch gs_client where it is USED (in the 'logs' module)
    with patch('app.sheets.logs.gs_client', autospec=True) as mock_client:
        yield mock_client

def test_append_new_user(mock_gs_client: MagicMock):
    """Тест: append_new_user вызывает gs_client с правильными данными."""
    # FIX 1: Use field aliases for User model
    user = User(user_id=123, user_name="Test User", phone="12345", role=UserRole.CLIENT)
    logs.append_new_user(user)
    # Note: Accessing attributes still works with python names (user.id)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.USERS,
        [user.id, user.name, user.phone, user.role.value]
    )

def test_append_pond(mock_gs_client: MagicMock):
    """Тест: append_pond вызывает gs_client с правильными данными."""
    pond = Pond(pond_id="P-TEST", name="Test Pond", type="pool", is_active=True)
    logs.append_pond(pond)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.PONDS, pond.to_sheet_row()
    )

def test_append_product(mock_gs_client: MagicMock):
    """Тест: append_product вызывает gs_client с правильными данными."""
    product = Product(product_id="PROD-TEST", name="Fish", description="Fresh", price=150.0, unit="kg", is_available=True)
    logs.append_product(product)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.PRODUCTS,
        product.to_sheet_row() # Using to_sheet_row() is more robust
    )

def test_append_feed_type(mock_gs_client: MagicMock):
    """Тест: append_feed_type вызывает gs_client с правильными данными."""
    # FIX 1: Use field alias for FeedType model
    feed_type = FeedType(feed_id="FEED-TEST", name="Starter", is_active=True)
    logs.append_feed_type(feed_type)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.FEED_TYPES, feed_type.to_sheet_row()
    )

def test_append_water_quality(mock_gs_client: MagicMock):
    """Тест: append_water_quality вызывает gs_client с правильными данными."""
    row = WaterQualityRow(ts=datetime.now(), pond_id="P1", dissolved_O2_mgL=8.5, temperature_C=15, user="tester")
    logs.append_water_quality(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.WATER_QUALITY_LOG, row.to_sheet_row()
    )

def test_append_stock_move(mock_gs_client: MagicMock):
    """Тест: append_stock_move вызывает gs_client с правильными данными."""
    row = StockMoveRow(
        ts=datetime.now(), feed_type_id="F1", feed_type_name="Grower",
        move_type=StockMoveType.INCOME, mass_kg=100.0, reason="purchase", user="tester"
    )
    logs.append_stock_move(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.STOCK_MOVES_LOG, row.to_sheet_row()
    )

def test_append_feeding(mock_gs_client: MagicMock):
    """Тест: append_feeding вызывает gs_client с правильными данными."""
    row = FeedingRow(ts=datetime.now(), pond_id="P1", feed_type="Starter", mass_kg=25.5, user="tester")
    logs.append_feeding(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.FEEDING_LOG, row.to_sheet_row()
    )

def test_append_sales_order(mock_gs_client: MagicMock):
    """Тест: append_sales_order вызывает gs_client с правильными данными."""
    row = SalesOrderRow(order_id="ORD-1", ts=datetime.now(), client_id=123, client_name="Client", phone="555", total_amount=500.0)
    logs.append_sales_order(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.SALES_ORDERS, row.to_sheet_row()
    )

def test_append_sales_order_item(mock_gs_client: MagicMock):
    """Тест: append_sales_order_item вызывает gs_client с правильными данными."""
    row = SalesOrderItemRow(order_id="ORD-1", product_id="P1", product_name="Карп", quantity=5, price_per_unit=100)
    logs.append_sales_order_item(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.SALES_ORDER_ITEMS, row.to_sheet_row()
    )

def test_append_weighing(mock_gs_client: MagicMock):
    """Тест: append_weighing вызывает gs_client с правильными данными."""
    row = WeighingRow(ts=datetime.now(), pond_id="P1", avg_weight_g=350.5, user="tester")
    logs.append_weighing(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.WEIGHING_LOG, row.to_sheet_row()
    )

def test_append_fish_move(mock_gs_client: MagicMock):
    """Тест: append_fish_move вызывает gs_client с правильными данными."""
    row = FishMoveRow(ts=datetime.now(), pond_id="P1", move_type=FishMoveType.SALE, quantity=100, user="tester")
    logs.append_fish_move(row)
    mock_gs_client.append_row.assert_called_once_with(
        settings.SHEETS.FISH_MOVES_LOG, row.to_sheet_row()
    )