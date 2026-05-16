from pathlib import Path
from telegram import Update
from telegram.ext import ContextTypes
from .config import MODELS, AGENT_HOME, SESSION_MARKER, MAX_FILE_SIZE
from .utils import sanitize_prompt, new_session, run_process
from .media import extract_file_info, download_file, maybe_transcribe
from .agent import execute_task
from .state import (
    set_model_key, toggle_voice, set_search_query,
    get_pending_action, clear_pending_action, set_pending_action,
)
from .messaging import send_text
from .auth import authorized
import asyncio


@authorized
async def handle_voice_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    enabled = toggle_voice()
    await send_text(f"🔊 Voice output {'enabled' if enabled else 'disabled'}.", update)


@authorized
async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .status import build_status_text
    from .menu import build_status_menu
    msg = await build_status_text()
    await update.message.reply_text(msg, reply_markup=build_status_menu())


@authorized
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_obj, file_name, is_voice = extract_file_info(update.message)

    if not file_obj:
        await send_text("⚠️ Unsupported file type.", update)
        return

    if (file_obj.file_size or 0) > MAX_FILE_SIZE:
        await send_text(f"⚠️ File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB", update)
        return

    try:
        file_path = await download_file(file_obj, file_name)
        await send_text(f"✅ File saved: {file_path}", update)

        transcript = await maybe_transcribe(file_path, is_voice, update, send_text)
        if transcript:
            asyncio.create_task(execute_task(transcript, update, None, "Running agent from transcript..."))
    except Exception as e:
        await send_text(f"❌ Failed to download file: {e}", update)


@authorized
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    pending = get_pending_action(user_id)

    if pending:
        if pending["action"] == "scheduler_add":
            user_input = update.message.text.strip()
            clear_pending_action(user_id)
            if not user_input:
                await send_text("⚠️ Input cannot be empty.", update)
                return
            asyncio.create_task(execute_task(user_input, update, None))
            return

        if pending["action"] == "scheduler_edit":
            user_input = update.message.text.strip()
            old_task_id = pending["data"].get("task_id")
            clear_pending_action(user_id)
            if not user_input:
                await send_text("⚠️ Input cannot be empty.", update)
                return
            from .scheduler import load_tasks, save_tasks
            tasks = load_tasks()
            tasks = [t for t in tasks if t.get("id") != old_task_id]
            save_tasks(tasks)
            await send_text("🗑️ Old task deleted, creating new one...", update)
            asyncio.create_task(execute_task(user_input, update, None))
            return

        if pending["action"] == "scheduler_search":
            keyword = update.message.text.strip()
            clear_pending_action(user_id)
            if not keyword:
                await send_text("⚠️ Keyword cannot be empty.", update)
                return
            set_search_query(user_id, keyword)

            from .scheduler import load_tasks
            from .menu import build_scheduler_tasks_menu
            _TASK_PAGE_SIZE = 8
            all_tasks = load_tasks()
            kw = keyword.lower()
            filtered = [t for t in all_tasks if kw in t.get("prompt", "").lower() or kw in t.get("id", "").lower()]

            if not filtered:
                await send_text(f"🔍 No results for \"{keyword}\".", update)
                return

            total = len(filtered)
            total_pages = (total + _TASK_PAGE_SIZE - 1) // _TASK_PAGE_SIZE
            page_tasks = filtered[:_TASK_PAGE_SIZE]
            await update.message.reply_text(
                f"🔍 Results for \"{keyword}\":",
                reply_markup=build_scheduler_tasks_menu(page_tasks, "list", 1, total_pages)
            )
            return

        if pending["action"] == "session_rename":
            new_name = update.message.text.strip()
            session_id = pending["data"].get("session_id")
            clear_pending_action(user_id)
            if not new_name:
                await send_text("⚠️ Name cannot be empty.", update)
                return
            if not session_id:
                await send_text("⚠️ Session ID missing.", update)
                return
            import sqlite3
            from .config import OPENCODE_DB_PATH
            conn = sqlite3.connect(OPENCODE_DB_PATH)
            try:
                conn.execute("UPDATE session SET title = ? WHERE id = ?", (new_name, session_id))
                conn.commit()
                affected = conn.total_changes
            finally:
                conn.close()
            if affected == 0:
                await send_text("⚠️ Session not found.", update)
                return
            await send_text(f"✅ Session renamed to: {new_name}", update)
            return

        if pending["action"] == "sessions_search":
            keyword = update.message.text.strip()
            clear_pending_action(user_id)
            if not keyword:
                await send_text("⚠️ Keyword cannot be empty.", update)
                return
            set_search_query(user_id, keyword)

            from .menu import build_sessions_list_menu, search_sessions_content
            _PAGE_SIZE = 10
            filtered = await search_sessions_content(keyword)
            if not filtered:
                await send_text(f"🔍 No results for \"{keyword}\".", update)
                return

            total = len(filtered)
            total_pages = (total + _PAGE_SIZE - 1) // _PAGE_SIZE
            page_sessions = filtered[:_PAGE_SIZE]
            await update.message.reply_text(
                f"🔍 Results for \"{keyword}\":",
                reply_markup=build_sessions_list_menu(page_sessions, 1, total_pages, nav_prefix="sessions:search")
            )
            return

    prompt = sanitize_prompt(update.message.text)
    if not prompt:
        await send_text("⚠️ Empty message.", update)
        return

    asyncio.create_task(execute_task(prompt, update, None))


def _make_model_handler(key: str):
    @authorized
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        set_model_key(key)
        await send_text(f"✅ Switched to {MODELS[key]}", update)
    return handler


handle_free = _make_model_handler("free")
handle_flash = _make_model_handler("flash")
handle_pro = _make_model_handler("pro")


@authorized
async def handle_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .state import get_running_process, set_stop_requested
    proc = get_running_process()
    if proc is None:
        await send_text("⚠️ No task is currently running.", update)
        return
    set_stop_requested(True)
    try:
        proc.kill()
    except Exception:
        pass
    await send_text("🛑 Stopping current task...", update)


@authorized
async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_session()
    await send_text("✅ New session started.", update)


@authorized
async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = ["opencode", "session", "list"]
    if context.args:
        cmd.extend(["-n", context.args[0]])

    rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)
    if rc != 0 or not stdout.strip():
        await send_text("⚠️ Failed to retrieve sessions.", update)
        return

    await send_text(f"📋 Session History:\n{stdout.strip()}", update)


@authorized
async def handle_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await send_text("⚠️ Usage: /continue <session-id>", update)
        return

    Path(SESSION_MARKER).write_text(context.args[0])
    await send_text(f"✅ Continuing session: {context.args[0]}", update)


@authorized
async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args or len(context.args) != 1:
        await send_text("⚠️ Usage: /delete <session-id>", update)
        return

    session_id = context.args[0]
    rc, stdout, stderr = await run_process(["opencode", "session", "delete", session_id], cwd=AGENT_HOME)
    if rc != 0:
        await send_text(f"⚠️ Failed to delete session: {stderr.strip() or 'unknown error'}", update)
        return
    await send_text(f"✅ Session deleted: {session_id}", update)


@authorized
async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_text(
        "Available commands:\n"
        "/menu - Show interactive menu\n"
        "/help - Show this help\n"
        "/status - Show bot health info\n"
        "/history [n] - Show session history (latest n, default all)\n"
        "/continue <id> - Continue a specific session\n"
        "/delete <id> - Delete a specific session\n"
        "/new - New session\n"
        "/cancel - Stop running agent task\n"
        "/free - Use free model\n"
        "/flash - Use deepseek-v4-flash model\n"
        "/pro - Use deepseek-v4-pro model\n"
        "/voice - Toggle voice output (TTS)\n"
        "Any other message - Run agent\n",
        update
    )
