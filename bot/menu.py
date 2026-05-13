import shutil
import uuid
import psutil
from datetime import datetime
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .config import AUTHORIZED_USER_ID, MODELS, AGENT_HOME, SESSION_MARKER
from .utils import new_session, run_process
from .state import set_model_key, toggle_voice, is_voice_enabled, get_model_key, get_bot_start_time, get_scheduler_status, get_pending_action, clear_pending_action


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


async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await update.message.reply_text("❌ Unauthorized.")
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
        msg = (
            "📅 Add a scheduled task by sending me a natural language prompt, e.g.:\n\n"
            "\"提醒我每天早上7点起床\"\n"
            "\"remind me to check email tomorrow at 9am\"\n"
            "\"每天下午3点查询大盘数据\"\n\n"
            "I'll parse the time and schedule it for you."
        )
        await query.edit_message_text(msg, reply_markup=build_scheduler_menu())

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
