from app.sheets.client import gs_client
from app.models.user import User
from app.models.pond import Pond
from app.models.product import Product
from app.models.water import WaterQualityRow
from app.models.feeding import FeedingRow, FeedType 
from app.models.order import SalesOrderRow, SalesOrderItemRow
from app.models.weighing import WeighingRow
from app.models.fish import FishMoveRow
from app.models.stock import StockMoveRow
from app.config.settings import settings

def append_new_user(user: User):
    gs_client.append_row(settings.SHEETS.USERS, [user.id, user.name, user.phone, user.role.value])

def append_pond(pond: Pond):
    gs_client.append_row(settings.SHEETS.PONDS, pond.to_sheet_row())

def append_product(product: Product):
    gs_client.append_row(
        settings.SHEETS.PRODUCTS, 
        [product.id, product.name, product.description, product.price, product.unit, True]
    )

def append_feed_type(feed_type: FeedType): # Новая функция для добавления типа корма
    gs_client.append_row(settings.SHEETS.FEED_TYPES, feed_type.to_sheet_row())

def append_water_quality(row: WaterQualityRow):
    gs_client.append_row(settings.SHEETS.WATER_QUALITY_LOG, row.to_sheet_row())

def append_feeding(row: FeedingRow):
    gs_client.append_row(settings.SHEETS.FEEDING_LOG, row.to_sheet_row())

def append_sales_order(row: SalesOrderRow):
    gs_client.append_row(settings.SHEETS.SALES_ORDERS, row.to_sheet_row())

def append_sales_order_item(row: SalesOrderItemRow):
    gs_client.append_row(settings.SHEETS.SALES_ORDER_ITEMS, row.to_sheet_row())

def append_weighing(row: WeighingRow):
    gs_client.append_row(settings.SHEETS.WEIGHING_LOG, row.to_sheet_row())

def append_fish_move(row: FishMoveRow):
    gs_client.append_row(settings.SHEETS.FISH_MOVES_LOG, row.to_sheet_row())

def append_stock_move(row: StockMoveRow):
    gs_client.append_row(settings.SHEETS.STOCK_MOVES_LOG, row.to_sheet_row())