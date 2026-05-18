#!/usr/bin/env python3
import sys
import asyncio
import logging
import time
from telegram import BotCommand
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
    handle_delete,
    handle_free,
    handle_flash,
    handle_pro,
    handle_new,
    handle_stop,
    handle_message,
    handle_file,
    handle_voice_toggle,
    handle_restart,
)
from bot.menu import handle_menu, handle_callback, build_main_menu
from bot.state import set_bot_start_time, clear_restart, is_restart_pending
from bot.scheduler import scheduler_loop
from bot.utils import health_check_loop


COMMANDS = [
    ("menu", handle_menu, "Show interactive menu"),
    ("help", handle_help, "Show help"),
    ("status", handle_status, "Show bot health info"),
    ("history", handle_history, "Show session history"),
    ("continue", handle_continue, "Continue a session"),
    ("delete", handle_delete, "Delete a session"),
    ("new", handle_new, "New session"),
    ("cancel", handle_stop, "Stop running agent task"),
    ("free", handle_free, "Use free model"),
    ("flash", handle_flash, "Use deepseek-v4-flash model"),
    ("pro", handle_pro, "Use deepseek-v4-pro model"),
    ("voice", handle_voice_toggle, "Toggle voice output"),
    ("restart", handle_restart, "Restart bot"),
]


async def error_handler(update, context):
    logging.error(f"Exception: {context.error}")


async def post_init(app):
    from datetime import datetime
    set_bot_start_time(datetime.now())
    try:
        await app.bot.set_my_commands([
            BotCommand(cmd, desc) for cmd, _, desc in COMMANDS
        ])
    except Exception as e:
        logging.error(f"Failed to set commands: {e}")
    asyncio.create_task(scheduler_loop(app))
    asyncio.create_task(health_check_loop(app))
    await app.bot.send_message(
        chat_id=AUTHORIZED_USER_ID,
        text="🚀 Agent ready (opencode backend).",
        reply_markup=build_main_menu()
    )


async def run_app(app):
    clear_restart()

    await app.initialize()
    if app.post_init:
        await app.post_init(app)

    await app.updater.start_polling(drop_pending_updates=True)
    await app.start()

    logging.info("Bot started, polling...")

    while not is_restart_pending():
        await asyncio.sleep(1)

    await asyncio.sleep(0.5)

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


def build_app():
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .proxy(PROXY_URL)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_read_timeout(60)
        .build()
    )

    for cmd, handler, _ in COMMANDS:
        app.add_handler(CommandHandler(cmd, handler))

    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE,
        handle_file
    ))

    app.add_error_handler(error_handler)
    app.post_init = post_init
    return app


def main():
    if not TOKEN or not AUTHORIZED_USER_ID:
        logging.error("TOKEN and AUTHORIZED_USER_ID must be set")
        sys.exit(1)

    while True:
        try:
            app = build_app()
            asyncio.run(run_app(app))
        except Exception as e:
            logging.error(f"App error: {e}")

        logging.warning("Waiting 5s before restart...")
        time.sleep(5)


if __name__ == "__main__":
    main()
