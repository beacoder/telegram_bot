import asyncio
import os
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .config import TELEGRAM_MAX_LENGTH, AUTHORIZED_USER_ID, MAX_FILE_SIZE, MODELS, AGENT_HOME, SESSION_MARKER
from .utils import sanitize_prompt, new_session, run_process
from .media import extract_file_info, download_file, maybe_transcribe
from .agent import execute_task
from .state import set_model_key, toggle_voice, is_voice_enabled, get_pending_action, clear_pending_action, set_search_query
from .media import text_to_speech, validate_piper
from pathlib import Path
import uuid


async def send_text(text: str, update: Update = None, app=None, reply_markup=None):
    if not text or not text.strip():
        return
    chunks = [
        text[i:i + TELEGRAM_MAX_LENGTH]
        for i in range(0, len(text), TELEGRAM_MAX_LENGTH)
    ]
    for i, chunk in enumerate(chunks):
        kw = {}
        if reply_markup and i == len(chunks) - 1:
            kw["reply_markup"] = reply_markup
        if update:
            await update.message.reply_text(chunk, **kw)
        elif app:
            await app.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=chunk, **kw)
        await asyncio.sleep(0.6)


async def send_audio(audio_path: str, update: Update = None, app=None):
    if not os.path.exists(audio_path):
        return
    try:
        with open(audio_path, "rb") as f:
            if update:
                await update.message.reply_voice(voice=f)
            elif app:
                await app.bot.send_voice(chat_id=AUTHORIZED_USER_ID, voice=f)
    except Exception as e:
        await send_text(f"Failed to send audio: {e}", update, app)


async def send_files(update: Update = None, app=None):
    from .config import AGENT_MEDIA_DIR
    if not os.path.exists(AGENT_MEDIA_DIR):
        return
    files = sorted(
        [os.path.join(AGENT_MEDIA_DIR, f) for f in os.listdir(AGENT_MEDIA_DIR)],
        key=os.path.getmtime
    )
    for path in files:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                if update:
                    await update.message.reply_document(document=f)
                elif app:
                    await app.bot.send_document(chat_id=AUTHORIZED_USER_ID, document=f)
        except Exception as e:
            await send_text(f"❌ Failed to send file: {path}", update, app)


async def handle_voice_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    enabled = toggle_voice()
    status = "enabled" if enabled else "disabled"
    await send_text(f"🔊 Voice output {status}.", update)


async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    from .status import build_status_text
    from .menu import build_status_menu
    msg = await build_status_text()
    await update.message.reply_text(msg, reply_markup=build_status_menu())


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

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
            await execute_task(transcript, update, None, "Running agent from transcript...")
    except Exception as e:
        await send_text(f"❌ Failed to download file: {e}", update)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    user_id = update.message.from_user.id
    pending = get_pending_action(user_id)

    if pending:
        if pending["action"] == "scheduler_add_prompt":
            task_time = pending["data"]["time"]
            task_prompt = update.message.text
            from .scheduler import load_tasks, save_tasks
            tasks = load_tasks()
            task_id = str(uuid.uuid4())[:8]
            tasks.append({
                "id": task_id,
                "run_at": task_time,
                "prompt": task_prompt,
                "done": False
            })
            save_tasks(tasks)
            clear_pending_action(user_id)
            await send_text(f"✅ Task scheduled: {task_prompt[:50]}...", update)
            return

        if pending["action"] == "sessions_search":
            keyword = update.message.text.strip()
            clear_pending_action(user_id)
            if not keyword:
                await send_text("⚠️ Keyword cannot be empty.", update)
                return
            set_search_query(user_id, keyword)

            from .menu import build_sessions_list_menu
            _PAGE_SIZE = 10
            cmd = ["opencode", "session", "list", "-n", "50"]
            rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)
            if rc != 0 or not stdout.strip():
                await send_text("⚠️ No sessions found.", update)
                return

            lines = [l.strip() for l in stdout.strip().split("\n") if l.strip()]
            all_sessions = []
            for l in lines:
                if not l.startswith("ses_"):
                    continue
                parts = l.split()
                sid = parts[0]
                title = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1] if len(parts) > 1 else sid
                all_sessions.append((sid, title))

            kw = keyword.lower()
            filtered = [(sid, t) for sid, t in all_sessions if kw in sid.lower() or kw in t.lower()]
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

    await execute_task(prompt, update, None)


async def handle_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("free")
    await send_text(f"✅ Switched to {MODELS['free']}", update)


async def handle_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("flash")
    await send_text(f"✅ Switched to {MODELS['flash']}", update)


async def handle_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("pro")
    await send_text(f"✅ Switched to {MODELS['pro']}", update)


async def handle_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    new_session()
    await send_text("✅ New session started.", update)


async def handle_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    args = context.args
    cmd = ["opencode", "session", "list"]
    if args:
        cmd.extend(["-n", args[0]])

    rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)

    if rc != 0 or not stdout.strip():
        await send_text("⚠️ Failed to retrieve sessions.", update)
        return

    await send_text(f"📋 Session History:\n{stdout.strip()}", update)


async def handle_continue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    args = context.args
    if not args or len(args) != 1:
        await send_text("⚠️ Usage: /continue <session-id>", update)
        return

    session_id = args[0]
    Path(SESSION_MARKER).write_text(session_id)
    await send_text(f"✅ Continuing session: {session_id}", update)


async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    args = context.args
    if not args or len(args) != 1:
        await send_text("⚠️ Usage: /delete <session-id>", update)
        return

    session_id = args[0]
    rc, stdout, stderr = await run_process(["opencode", "session", "delete", session_id], cwd=AGENT_HOME)
    if rc != 0:
        await send_text(f"⚠️ Failed to delete session: {stderr.strip() or 'unknown error'}", update)
        return
    await send_text(f"✅ Session deleted: {session_id}", update)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    await send_text(
        "Available commands:\n"
        "/menu - Show interactive menu\n"
        "/help - Show this help\n"
        "/status - Show bot health info\n"
        "/history [n] - Show session history (latest n, default all)\n"
        "/continue <id> - Continue a specific session\n"
        "/delete <id> - Delete a specific session\n"
        "/new - New session\n"
        "/free - Use free model\n"
        "/flash - Use deepseek-v4-flash model\n"
        "/pro - Use deepseek-v4-pro model\n"
        "/voice - Toggle voice output (TTS)\n"
        "Any other message - Run agent\n",
        update
    )
