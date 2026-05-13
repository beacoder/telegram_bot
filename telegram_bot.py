#!/usr/bin/env python3
import sys
import asyncio
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from bot.config import TOKEN, AUTHORIZED_USER_ID, PROXY_URL
from bot.handlers import (
    handle_help,
    handle_status,
    handle_history,
    handle_continue,
    handle_free,
    handle_flash,
    handle_pro,
    handle_new,
    handle_message,
    handle_file,
    handle_voice_toggle,
)
from bot.menu import handle_menu, handle_callback, build_main_menu
from bot.state import set_bot_start_time
from bot.scheduler import scheduler_loop
from bot.handlers import send_text


def main():
    if not TOKEN or not AUTHORIZED_USER_ID:
        logging.error("TOKEN and AUTHORIZED_USER_ID must be set")
        sys.exit(1)

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .proxy(PROXY_URL)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_read_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("help", handle_help))
    app.add_handler(CommandHandler("status", handle_status))
    app.add_handler(CommandHandler("history", handle_history))
    app.add_handler(CommandHandler("continue", handle_continue))
    app.add_handler(CommandHandler("free", handle_free))
    app.add_handler(CommandHandler("flash", handle_flash))
    app.add_handler(CommandHandler("pro", handle_pro))
    app.add_handler(CommandHandler("new", handle_new))
    app.add_handler(CommandHandler("voice", handle_voice_toggle))
    app.add_handler(CommandHandler("menu", handle_menu))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
        handle_file
    ))

    async def error_handler(update, context):
        logging.error(f"Exception: {context.error}")
    app.add_error_handler(error_handler)

    async def _post_init(app):
        from datetime import datetime
        set_bot_start_time(datetime.now())
        asyncio.create_task(scheduler_loop(app))
        await app.bot.send_message(
            chat_id=AUTHORIZED_USER_ID,
            text="🚀 Agent ready (opencode backend).",
            reply_markup=build_main_menu()
        )
    app.post_init = _post_init

    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
