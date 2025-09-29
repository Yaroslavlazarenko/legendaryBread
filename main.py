import asyncio
from telegram.ext import ApplicationBuilder, PicklePersistence
from app.config.settings import settings
from app.utils.logger import log
from app.bot.handlers import register_handlers

def main() -> None:  # <-- FIX 1: Not an async function
    """Основная функция для запуска бота."""
    log.info("Запуск бота...")

    # Создание приложения
    persistence = PicklePersistence(filepath="bot_persistence")
    application = ApplicationBuilder().token(settings.BOT_TOKEN).persistence(persistence).build()

    # Регистрация обработчиков
    register_handlers(application)
    log.info("Обработчики успешно зарегистрированы.")

    # Запуск бота
    # Note: The webhook logic here is async, but run_polling is not.
    # For simplicity, we'll focus on run_polling which is what you're using.
    if settings.WEBHOOK_URL:
        # This part requires an async context to run properly.
        # However, since you are running in polling mode, we will focus on that.
        # A more advanced setup would handle this branching differently.
        log.error("Webhook mode is configured but this script is running synchronously for polling.")
        log.error("Please run in a proper async context for webhooks.")
        return
    else:
        # Режим опроса для локальной разработки
        log.info("Запуск в режиме polling...")
        # FIX 2: run_polling() is a blocking, synchronous call. No await needed.
        application.run_polling()

if __name__ == "__main__":
    try:
        main() # <-- FIX 3: Call main() directly
    except (KeyboardInterrupt, SystemExit):
        log.info("Бот остановлен.")