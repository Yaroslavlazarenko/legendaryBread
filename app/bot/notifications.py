from telegram.ext import ContextTypes
from telegram.error import Forbidden

from app.sheets import references
from app.utils.logger import log

async def notify_admins(context: ContextTypes.DEFAULT_TYPE, message: str, parse_mode: str = None):
    """
    Отправляет сообщение всем администраторам, у которых включены уведомления.
    """
    admin_users = references.get_admins()
    if not admin_users:
        log.warning("В системе не найдены администраторы для отправки уведомления.")
        return

    for admin in admin_users:
        # --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Проверяем флаг ---
        if not admin.notifications_enabled:
            continue  # Пропускаем админа, если у него выключены уведомления
        
        try:
            await context.bot.send_message(
                chat_id=admin.id,
                text=message,
                parse_mode=parse_mode
            )
        except Forbidden:
            log.warning(f"Не удалось отправить уведомление администратору {admin.name} ({admin.id}). Бот заблокирован.")
        except Exception as e:
            log.error(f"Непредвиденная ошибка при отправке уведомления администратору {admin.id}: {e}")