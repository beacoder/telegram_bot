import asyncio
import os
import shutil
import tempfile
import psutil
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from .config import TELEGRAM_MAX_LENGTH, AUTHORIZED_USER_ID, MAX_FILE_SIZE, MODELS, AGENT_HOME, SESSION_MARKER
from .utils import sanitize_prompt, new_session, run_process
from .media import extract_file_info, download_file, maybe_transcribe
from .agent import execute_task
from .state import set_model_key, toggle_voice, is_voice_enabled, get_model_key, get_bot_start_time, get_scheduler_status, set_pending_action, get_pending_action, clear_pending_action
from .media import text_to_speech, validate_piper
from pathlib import Path
from datetime import datetime, timedelta
import uuid


def build_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Models", callback_data="menu:ai")],
        [InlineKeyboardButton("📂 Sessions", callback_data="menu:sessions")],
        [InlineKeyboardButton("📅 Scheduler", callback_data="menu:scheduler")],
        [InlineKeyboardButton("🎤 Voice", callback_data="menu:voice")],
        [InlineKeyboardButton("📊 Status", callback_data="menu:status")],
    ])


def build_ai_menu():
    current = get_model_key()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Free" if current == "free" else "Free", callback_data="ai:free")],
        [InlineKeyboardButton(f"✅ Flash" if current == "flash" else "Flash", callback_data="ai:flash")],
        [InlineKeyboardButton(f"✅ Pro" if current == "pro" else "Pro", callback_data="ai:pro")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_sessions_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 New Session", callback_data="sessions:new")],
        [InlineKeyboardButton("📜 Continue Session", callback_data="sessions:continue")],
        [InlineKeyboardButton("📋 View History", callback_data="sessions:history")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_scheduler_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 View Tasks", callback_data="scheduler:list")],
        [InlineKeyboardButton("➕ Add Task", callback_data="scheduler:add")],
        [InlineKeyboardButton("🗑️ Delete Task", callback_data="scheduler:delete")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_voice_menu():
    enabled = is_voice_enabled()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔊 Voice: {'ON' if enabled else 'OFF'}", callback_data="voice:toggle")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_scheduler_time_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Tomorrow", callback_data="scheduler:add:tomorrow")],
        [InlineKeyboardButton("📆 Next Week", callback_data="scheduler:add:week")],
        [InlineKeyboardButton("✏️ Custom", callback_data="scheduler:add:custom")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:scheduler")],
    ])


def build_sessions_list_menu(sessions: list):
    buttons = []
    for sid, title in sessions[:10]:
        label = f"{title[:35]}…" if len(title) > 35 else title
        buttons.append([InlineKeyboardButton(label, callback_data=f"session:continue:{sid}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(buttons)


def build_scheduler_tasks_menu(tasks: list, mode: str = "list"):
    buttons = []
    for i, task in enumerate(tasks):
        tid = task.get("id") or f"_idx_{i}"
        label = task.get("prompt", "")[:25] + "..." if len(task.get("prompt", "")) > 25 else task.get("prompt", "")
        if mode == "delete":
            buttons.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"scheduler:delete:{tid}")])
        else:
            done = "✅" if task.get("done") else "⏳"
            buttons.append([InlineKeyboardButton(f"{done} {label}", callback_data=f"scheduler:view:{tid}")])
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:scheduler")])
    return InlineKeyboardMarkup(buttons)


def build_status_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


async def send_text(text: str, update: Update = None, app=None):
    if not text or not text.strip():
        return
    chunks = [
        text[i:i + TELEGRAM_MAX_LENGTH]
        for i in range(0, len(text), TELEGRAM_MAX_LENGTH)
    ]
    for chunk in chunks:
        if update:
            await update.message.reply_text(chunk)
        elif app:
            await app.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=chunk)
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

    start = get_bot_start_time()
    if start:
        delta = datetime.now() - start
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime = f"{hours}h {minutes}m {seconds}s"
    else:
        uptime = "N/A"

    model = MODELS.get(get_model_key(), "unknown")
    scheduler = get_scheduler_status()

    try:
        cpu_pct = f"{psutil.cpu_percent(interval=0.1):.1f}"
        mem = psutil.virtual_memory()
        mem_info = f"{round(mem.used / (1024**3), 1)}G / {round(mem.total / (1024**3), 1)}G ({mem.percent:.1f}%)"
    except Exception:
        cpu_pct = "N/A"
        mem_info = "N/A"

    try:
        disk = shutil.disk_usage(Path(AGENT_HOME).anchor or "/")
        used_pct = disk.used / disk.total * 100
        disk_info = f"{round(disk.used / (1024**3), 1)}G / {round(disk.total / (1024**3), 1)}G ({used_pct:.1f}%)"
    except Exception:
        disk_info = "N/A"

    msg = (
        f"📊 Bot Status\n"
        f"─────────────\n"
        f"Uptime:    {uptime}\n"
        f"Model:     {model}\n"
        f"Scheduler: {scheduler}\n"
        f"CPU:       {cpu_pct}%\n"
        f"Memory:    {mem_info}\n"
        f"Disk:      {disk_info}"
    )
    await send_text(msg, update)


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


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    await update.message.reply_text("🖥️ Main Menu", reply_markup=build_main_menu())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id != AUTHORIZED_USER_ID:
        await query.edit_message_text("❌ Unauthorized.")
        return

    data = query.data

    pending = get_pending_action(user_id)

    if pending:
        if pending["action"] == "scheduler_add_prompt":
            task_time = pending["data"]["time"]
            task_prompt = query.data
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
            await query.edit_message_text(f"✅ Task scheduled: {task_prompt[:50]}...", reply_markup=build_scheduler_menu())
            return

    if data == "menu:main":
        await query.edit_message_text("🖥️ Main Menu", reply_markup=build_main_menu())
    elif data == "menu:ai":
        await query.edit_message_text("🧠 Select Model", reply_markup=build_ai_menu())
    elif data == "menu:sessions":
        await query.edit_message_text("📂 Sessions", reply_markup=build_sessions_menu())
    elif data == "menu:scheduler":
        await query.edit_message_text("📅 Scheduler", reply_markup=build_scheduler_menu())
    elif data == "menu:voice":
        await query.edit_message_text("🎤 Voice", reply_markup=build_voice_menu())
    elif data == "menu:status":
        start = get_bot_start_time()
        if start:
            delta = datetime.now() - start
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            uptime = f"{hours}h {minutes}m {seconds}s"
        else:
            uptime = "N/A"

        model = MODELS.get(get_model_key(), "unknown")
        scheduler = get_scheduler_status()

        try:
            cpu_pct = f"{psutil.cpu_percent(interval=0.1):.1f}"
            mem = psutil.virtual_memory()
            mem_info = f"{round(mem.used / (1024**3), 1)}G / {round(mem.total / (1024**3), 1)}G ({mem.percent:.1f}%)"
        except Exception:
            cpu_pct = "N/A"
            mem_info = "N/A"

        try:
            disk = shutil.disk_usage(Path(AGENT_HOME).anchor or "/")
            used_pct = disk.used / disk.total * 100
            disk_info = f"{round(disk.used / (1024**3), 1)}G / {round(disk.total / (1024**3), 1)}G ({used_pct:.1f}%)"
        except Exception:
            disk_info = "N/A"

        msg = (
            f"📊 Bot Status\n"
            f"─────────────\n"
            f"Uptime:    {uptime}\n"
            f"Model:     {model}\n"
            f"Scheduler: {scheduler}\n"
            f"CPU:       {cpu_pct}%\n"
            f"Memory:    {mem_info}\n"
            f"Disk:      {disk_info}"
        )
        await query.message.reply_text(msg, reply_markup=build_status_menu())

    elif data.startswith("ai:"):
        model = data.split(":")[1]
        set_model_key(model)
        await query.edit_message_text(f"✅ Switched to {MODELS.get(model, model)}", reply_markup=build_ai_menu())

    elif data == "sessions:new":
        new_session()
        await query.edit_message_text("✅ New session started", reply_markup=build_sessions_menu())

    elif data == "sessions:continue":
        cmd = ["opencode", "session", "list", "-n", "10"]
        rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)

        if rc != 0 or not stdout.strip():
            await query.edit_message_text("⚠️ No sessions found", reply_markup=build_sessions_menu())
            return

        lines = [l.strip() for l in stdout.strip().split("\n") if l.strip()]
        sessions = []
        for l in lines:
            if not l.startswith("ses_"):
                continue
            parts = l.split()
            sid = parts[0]
            title = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1] if len(parts) > 1 else sid
            sessions.append((sid, title))
        if not sessions:
            await query.edit_message_text("⚠️ No sessions found", reply_markup=build_sessions_menu())
            return

        await query.edit_message_text("Select a session to continue:", reply_markup=build_sessions_list_menu(sessions))

    elif data.startswith("session:continue:"):
        session_id = data.split(":")[-1]
        Path(SESSION_MARKER).write_text(session_id)
        await query.edit_message_text(f"✅ Continuing session: {session_id}", reply_markup=build_sessions_menu())

    elif data == "sessions:history":
        cmd = ["opencode", "session", "list", "-n", "10"]
        rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)

        if rc != 0 or not stdout.strip():
            await query.edit_message_text("⚠️ Failed to retrieve sessions.", reply_markup=build_sessions_menu())
            return

        lines = [l.strip() for l in stdout.strip().split("\n") if l.strip()]
        body = "\n".join(l for l in lines if l.startswith("ses_"))
        await query.message.reply_text(f"📋 Session History:\n{body}", reply_markup=build_sessions_menu())

    elif data == "voice:toggle":
        toggle_voice()
        enabled = is_voice_enabled()
        status = "enabled" if enabled else "disabled"
        await query.edit_message_text(f"🔊 Voice output {status}.", reply_markup=build_voice_menu())

    elif data == "scheduler:list":
        from .scheduler import load_tasks
        tasks = load_tasks()
        if not tasks:
            await query.edit_message_text("📋 No scheduled tasks", reply_markup=build_scheduler_menu())
            return
        await query.edit_message_text("📋 Scheduled Tasks:", reply_markup=build_scheduler_tasks_menu(tasks, "list"))

    elif data.startswith("scheduler:view:"):
        task_id = data.split(":")[-1]
        if task_id.startswith("_idx_"):
            await query.edit_message_text("⚠️ Task not found. Please refresh the task list.", reply_markup=build_scheduler_menu())
            return
        from .scheduler import load_tasks
        tasks = load_tasks()
        task = next((t for t in tasks if t.get("id") == task_id), None)
        if not task:
            await query.edit_message_text("⚠️ Task not found", reply_markup=build_scheduler_menu())
            return
        status = "✅ Done" if task.get("done") else "⏳ Pending"
        repeat = task.get("repeat", "None")
        msg = (
            f"📋 Task Detail\n"
            f"─────────────\n"
            f"Prompt: {task['prompt']}\n"
            f"Run at: {task['run_at']}\n"
            f"Status: {status}\n"
            f"Repeat: {repeat}"
        )
        await query.message.reply_text(msg, reply_markup=build_scheduler_menu())

    elif data == "scheduler:add":
        await query.edit_message_text("Select time for the task:", reply_markup=build_scheduler_time_menu())

    elif data == "scheduler:add:tomorrow":
        tomorrow = (datetime.now() + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        set_pending_action(user_id, "scheduler_add_prompt", {"time": tomorrow.strftime("%Y-%m-%d %H:%M")})
        await query.edit_message_text("📝 Please enter the task description:")

    elif data == "scheduler:add:week":
        next_week = (datetime.now() + timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
        set_pending_action(user_id, "scheduler_add_prompt", {"time": next_week.strftime("%Y-%m-%d %H:%M")})
        await query.edit_message_text("📝 Please enter the task description:")

    elif data == "scheduler:add:custom":
        await query.edit_message_text("📝 Please enter the task in format:\n/ schedule 2026-05-20 10:00 your task description")

    elif data == "scheduler:delete":
        from .scheduler import load_tasks
        tasks = load_tasks()
        if not tasks:
            await query.edit_message_text("📋 No scheduled tasks to delete", reply_markup=build_scheduler_menu())
            return
        await query.edit_message_text("🗑️ Select a task to delete:", reply_markup=build_scheduler_tasks_menu(tasks, "delete"))

    elif data.startswith("scheduler:delete:"):
        task_id = data.split(":")[-1]
        from .scheduler import load_tasks, save_tasks
        tasks = load_tasks()
        tasks = [t for t in tasks if t.get("id") != task_id]
        save_tasks(tasks)
        await query.edit_message_text("✅ Task deleted", reply_markup=build_scheduler_menu())


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
        "/new - New session\n"
        "/free - Use free model\n"
        "/flash - Use deepseek-v4-flash model\n"
        "/pro - Use deepseek-v4-pro model\n"
        "/voice - Toggle voice output (TTS)\n"
        "Any other message - Run agent\n",
        update
    )
