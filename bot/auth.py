from functools import wraps
from .config import AUTHORIZED_USER_ID


def authorized(func):
    @wraps(func)
    async def wrapper(update, context):
        if update.message.from_user.id != AUTHORIZED_USER_ID:
            await update.message.reply_text("❌ Unauthorized.")
            return
        return await func(update, context)
    return wrapper
