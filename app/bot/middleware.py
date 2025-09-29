from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from app.models.user import UserRole
from app.sheets.references import get_user_by_id

def restricted(allowed_roles: list[UserRole], self_register: bool = False):
    """
    Декоратор для ограничения доступа.
    Если self_register=True, то незарегистрированным пользователям будет предложена регистрация.
    """
    def decorator(func):
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id
            user = get_user_by_id(user_id)

            if not user:
                if self_register:
                    await update.message.reply_text(
                        "Вы не зарегистрированы в системе. "
                        "Чтобы начать, пожалуйста, пройдите регистрацию с помощью команды /register"
                    )
                else:
                    await update.message.reply_text("Вы не зарегистрированы в системе. Обратитесь к администратору.")
                return

            if user.role == UserRole.PENDING:
                await update.message.reply_text("Ваша заявка на регистрацию ожидает подтверждения администратором.")
                return

            if user.role not in allowed_roles:
                await update.message.reply_text("⛔️ У вас нет доступа к этой команде.")
                return
            
            context.user_data['current_user'] = user
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator