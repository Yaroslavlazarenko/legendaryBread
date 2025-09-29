import sys
from loguru import logger
from app.config.settings import settings

logger.remove()
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL.upper(),
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)
logger.add(
    "logs/error.log",
    level="ERROR",
    rotation="10 MB",
    compression="zip",
    enqueue=True,
    backtrace=True,
    diagnose=True
)

log = logger