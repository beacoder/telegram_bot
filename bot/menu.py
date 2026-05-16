from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from .config import AUTHORIZED_USER_ID, MODELS, AGENT_HOME, SESSION_MARKER, OPENCODE_DB_PATH
from .utils import new_session, run_process
from .state import set_model_key, toggle_voice, is_voice_enabled, get_model_key, set_pending_action, set_search_query, get_search_query
from .status import build_status_text
from .auth import authorized


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
        [InlineKeyboardButton("📋 View History", callback_data="sessions:history")],
        [InlineKeyboardButton("🔍 Search Session", callback_data="sessions:search")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_sessions_list_menu(sessions: list, page: int, total_pages: int, nav_prefix: str = "sessions:list"):
    buttons = []
    for sid, title in sessions:
        label = f"{title[:35]}…" if len(title) > 35 else title
        buttons.append([InlineKeyboardButton(label, callback_data=f"session:select:{sid}")])
    buttons.append(_build_nav(page, total_pages, nav_prefix))
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:sessions")])
    return InlineKeyboardMarkup(buttons)


def build_session_action_menu(session_id: str, title: str):
    label = f"{title[:35]}…" if len(title) > 35 else title
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📄 {label}", callback_data="sessions:noop")],
        [InlineKeyboardButton("▶️ Continue", callback_data=f"session:continue:{session_id}")],
        [InlineKeyboardButton("📝 Rename", callback_data=f"session:rename:{session_id}")],
        [InlineKeyboardButton("📋 Summary", callback_data=f"session:summary:{session_id}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"session:delete:{session_id}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:sessions")],
    ])


def build_scheduler_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 New Task", callback_data="scheduler:new")],
        [InlineKeyboardButton("📋 View Tasks", callback_data="scheduler:view")],
        [InlineKeyboardButton("🔍 Search Task", callback_data="scheduler:search")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def _build_nav(page: int, total_pages: int, prefix: str):
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{prefix}:{page - 1}"))
    nav.append(InlineKeyboardButton(f"Page {page}/{total_pages}", callback_data=f"{prefix}:noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"{prefix}:{page + 1}"))
    return nav


def build_scheduler_tasks_menu(tasks: list, mode: str = "list", page: int = 1, total_pages: int = 1):
    buttons = []
    for i, task in enumerate(tasks):
        tid = task.get("id") or f"_idx_{i}"
        label = task.get("prompt", "")[:25] + "..." if len(task.get("prompt", "")) > 25 else task.get("prompt", "")
        if mode == "delete":
            buttons.append([InlineKeyboardButton(f"🗑️ {label}", callback_data=f"scheduler:delete:{tid}")])
        else:
            done = "✅" if task.get("done") else "⏳"
            buttons.append([InlineKeyboardButton(f"{done} {label}", callback_data=f"scheduler:select:{tid}")])
    if mode == "list":
        buttons.append(_build_nav(page, total_pages, "scheduler:view"))
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="menu:scheduler")])
    return InlineKeyboardMarkup(buttons)


def build_scheduler_task_action_menu(task: dict):
    prompt = task.get("prompt", "")
    status = "✅ Done" if task.get("done") else "⏳ Pending"
    tid = task.get("id", "")
    label = f"{prompt[:25]}..." if len(prompt) > 25 else prompt
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{status}: {label}", callback_data="scheduler:noop")],
        [InlineKeyboardButton("✏️ Edit", callback_data=f"scheduler:edit:{tid}")],
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"scheduler:delete:{tid}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:scheduler")],
    ])


def build_voice_menu():
    enabled = is_voice_enabled()
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔊 Voice: {'ON' if enabled else 'OFF'}", callback_data="voice:toggle")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


def build_status_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh", callback_data="status:refresh")],
        [InlineKeyboardButton("⬅️ Back", callback_data="menu:main")],
    ])


# ── Callback Router ────────────────────────────────────────────────

EXACT_ROUTES = {}
PREFIX_ROUTES = []


def route(exact: str = None, prefix: str = None):
    def wrapper(func):
        if exact:
            EXACT_ROUTES[exact] = func
        if prefix:
            PREFIX_ROUTES.append((prefix, func))
        return func
    return wrapper


# ── Menu Renderer ──────────────────────────────────────────────────

async def render_menu(query, text, markup):
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception as e:
        if "message is not modified" in str(e).lower():
            await query.answer("No changes")
        else:
            raise


# ── Handler Functions ──────────────────────────────────────────────

@route(exact="menu:main")
async def _handle_menu_main(query):
    await render_menu(query, "🖥️ Main Menu", build_main_menu())


@route(exact="menu:ai")
async def _handle_menu_ai(query):
    await render_menu(query, "🧠 Select Model", build_ai_menu())


@route(exact="menu:sessions")
async def _handle_menu_sessions(query):
    await render_menu(query, "📂 Sessions", build_sessions_menu())


@route(exact="menu:scheduler")
async def _handle_menu_scheduler(query):
    await render_menu(query, "📅 Scheduler", build_scheduler_menu())


@route(exact="menu:voice")
async def _handle_menu_voice(query):
    await render_menu(query, "🎤 Voice", build_voice_menu())


@route(exact="menu:status")
@route(exact="status:refresh")
async def _handle_menu_status(query):
    await render_menu(query, await build_status_text(), build_status_menu())


@route(prefix="ai:")
async def _handle_ai_select(query, model_key):
    set_model_key(model_key)
    await render_menu(query, f"✅ Switched to {MODELS.get(model_key, model_key)}", build_ai_menu())


@route(exact="sessions:new")
async def _handle_sessions_new(query):
    new_session()
    await render_menu(query, "✅ New session started", build_sessions_menu())


_SESSION_PAGE_SIZE = 10
_TASK_PAGE_SIZE = 8


async def _render_sessions_list_page(query, page: int, all_sessions, title: str, nav_prefix: str):
    if not all_sessions:
        await render_menu(query, "⚠️ No sessions found", build_sessions_menu())
        return
    total = len(all_sessions)
    total_pages = (total + _SESSION_PAGE_SIZE - 1) // _SESSION_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * _SESSION_PAGE_SIZE
    page_sessions = all_sessions[start:start + _SESSION_PAGE_SIZE]
    await render_menu(query, title, build_sessions_list_menu(page_sessions, page, total_pages, nav_prefix=nav_prefix))


async def _fetch_all_sessions():
    cmd = ["opencode", "session", "list", "-n", "50"]
    rc, stdout, stderr = await run_process(cmd, cwd=AGENT_HOME)
    if rc != 0 or not stdout.strip():
        return []
    lines = [l.strip() for l in stdout.strip().split("\n") if l.strip()]
    result = []
    for l in lines:
        if not l.startswith("ses_"):
            continue
        parts = l.split()
        sid = parts[0]
        title = " ".join(parts[1:-1]) if len(parts) > 2 else parts[1] if len(parts) > 1 else sid
        result.append((sid, title))
    return result


# ── View History ──────────────────────────────────────────────────

@route(exact="sessions:history")
async def _handle_sessions_history(query):
    all_sessions = await _fetch_all_sessions()
    await _render_sessions_list_page(query, 1, all_sessions, "📋 Session History", "sessions:history")


@route(prefix="sessions:history:")
async def _handle_sessions_history_page(query, page_str):
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    all_sessions = await _fetch_all_sessions()
    await _render_sessions_list_page(query, page, all_sessions, "📋 Session History", "sessions:history")


# ── Search ────────────────────────────────────────────────────────

@route(exact="sessions:search")
async def _handle_sessions_search(query):
    user_id = query.from_user.id
    set_pending_action(user_id, "sessions_search")
    await render_menu(query, "🔍 Enter a keyword to search sessions:", InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Cancel", callback_data="menu:sessions")]
    ]))


async def search_sessions_content(keyword: str) -> list:
    import sqlite3
    conn = sqlite3.connect(OPENCODE_DB_PATH)
    try:
        kw = f"%{keyword.lower()}%"
        rows = conn.execute(
            "SELECT DISTINCT s.id, s.title FROM session s "
            "JOIN part p ON p.session_id = s.id "
            "WHERE s.project_id = 'global' "
            "AND (LOWER(p.data) LIKE ? OR LOWER(s.title) LIKE ? OR LOWER(s.id) LIKE ?) "
            "ORDER BY s.time_updated DESC LIMIT 50",
            (kw, kw, kw)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


async def _render_sessions_search_page(query, page: int, keyword: str):
    filtered = await search_sessions_content(keyword)
    if not filtered:
        await render_menu(query, f"🔍 No results for \"{keyword}\"", build_sessions_menu())
        return
    await _render_sessions_list_page(query, page, filtered, f"🔍 Results for \"{keyword}\"", "sessions:search")


@route(prefix="sessions:search:")
async def _handle_sessions_search_page(query, page_str):
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    keyword = get_search_query(query.from_user.id)
    if not keyword:
        await render_menu(query, "⚠️ Search expired, please try again.", build_sessions_menu())
        return
    await _render_sessions_search_page(query, page, keyword)


# ── Session Action Menu ───────────────────────────────────────────

@route(prefix="session:select:")
async def _handle_session_select(query, session_id):
    all_sessions = await _fetch_all_sessions()
    title = next((t for sid, t in all_sessions if sid == session_id), session_id)
    await render_menu(query, f"Session: {session_id}", build_session_action_menu(session_id, title))


@route(prefix="session:continue:")
async def _handle_session_continue(query, session_id):
    Path(SESSION_MARKER).write_text(session_id)
    await render_menu(query, f"✅ Continuing session: {session_id}", build_sessions_menu())


@route(prefix="session:delete:")
async def _handle_session_delete(query, session_id):
    rc, stdout, stderr = await run_process(["opencode", "session", "delete", session_id], cwd=AGENT_HOME)
    if rc != 0:
        await render_menu(query, f"⚠️ Failed to delete session: {stderr.strip() or 'unknown error'}", build_sessions_menu())
        return
    await render_menu(query, f"✅ Session deleted: {session_id}", build_sessions_menu())


@route(prefix="session:rename:")
async def _handle_session_rename(query, session_id):
    user_id = query.from_user.id
    set_pending_action(user_id, "session_rename", {"session_id": session_id})
    await render_menu(query, "📝 Enter a new name for this session:", InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Cancel", callback_data=f"session:select:{session_id}")]
    ]))


@route(prefix="session:summary:")
async def _handle_session_summary(query, session_id):
    await query.edit_message_text("📋 Summarizing session...")
    import sqlite3
    import json
    conn = sqlite3.connect(OPENCODE_DB_PATH)
    try:
        rows = conn.execute(
            "SELECT m.data, p.data FROM part p "
            "JOIN message m ON m.id = p.message_id "
            "WHERE p.session_id = ? ORDER BY p.time_created",
            (session_id,)
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        await query.message.reply_text("⚠️ No conversation found in this session.", reply_markup=build_sessions_menu())
        return

    parts = []
    for msg_data_str, part_data_str in rows:
        msg_data = json.loads(msg_data_str)
        role = msg_data.get("role", "unknown")
        part_data = json.loads(part_data_str)
        ptype = part_data.get("type", "")
        if ptype == "text":
            text = part_data.get("text", "")
            if text:
                parts.append(f"[{role.upper()}]: {text}")
        elif ptype == "reasoning":
            text = part_data.get("text", "")
            if text:
                parts.append(f"[REASONING]: {text[:200]}")

    if not parts:
        await query.message.reply_text("⚠️ No text content found in this session.", reply_markup=build_sessions_menu())
        return

    conversation = "\n\n".join(parts)
    combined = conversation[:6000]
    summary_prompt = f"Summarize this conversation concisely in 3-5 bullet points covering the key tasks and outcomes:\n\n{combined}"
    from .agent import run_agent
    summary = await run_agent(summary_prompt)
    await query.message.reply_text(f"📋 Session Summary:\n\n{summary}", reply_markup=build_session_action_menu(session_id, session_id))


@route(exact="voice:toggle")
async def _handle_voice_toggle(query):
    toggle_voice()
    enabled = is_voice_enabled()
    status = "enabled" if enabled else "disabled"
    await render_menu(query, f"🔊 Voice output {status}.", build_voice_menu())


@route(exact="scheduler:new")
@route(exact="scheduler:add")
async def _handle_scheduler_add(query):
    user_id = query.from_user.id
    set_pending_action(user_id, "scheduler_add")
    msg = (
        "📅 Send me a natural language prompt, e.g.:\n\n"
        "\"提醒我每天早上7点起床\"\n"
        "\"remind me to check email tomorrow at 9am\"\n"
        "\"每天下午3点查询大盘数据\"\n\n"
        "I'll use AI to parse the time and schedule it."
    )
    await render_menu(query, msg, InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Cancel", callback_data="menu:scheduler")]
    ]))


@route(exact="scheduler:view")
async def _handle_scheduler_view_list(query):
    await _render_scheduler_tasks_page(query, 1)


async def _render_scheduler_tasks_page(query, page: int):
    from .scheduler import load_tasks
    all_tasks = load_tasks()
    if not all_tasks:
        await render_menu(query, "📋 No scheduled tasks", build_scheduler_menu())
        return

    total = len(all_tasks)
    total_pages = (total + _TASK_PAGE_SIZE - 1) // _TASK_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * _TASK_PAGE_SIZE
    page_tasks = all_tasks[start:start + _TASK_PAGE_SIZE]

    await render_menu(query, "📋 Scheduled Tasks:", build_scheduler_tasks_menu(page_tasks, "list", page, total_pages))


@route(prefix="scheduler:view:")
async def _handle_scheduler_tasks_page(query, page_str):
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    await _render_scheduler_tasks_page(query, page)


@route(prefix="scheduler:select:")
async def _handle_scheduler_select(query, task_id):
    if task_id.startswith("_idx_"):
        await render_menu(query, "⚠️ Task not found. Please refresh the task list.", build_scheduler_menu())
        return
    from .scheduler import load_tasks
    tasks = load_tasks()
    task = next((t for t in tasks if t.get("id") == task_id), None)
    if not task:
        await render_menu(query, "⚠️ Task not found", build_scheduler_menu())
        return
    status = "✅ Done" if task.get("done") else "⏳ Pending"
    repeat = task.get("repeat", "None")
    prompt = task.get("prompt", "")
    msg = (
        f"📋 Task Detail\n"
        f"─────────────\n"
        f"Prompt: {prompt}\n"
        f"Run at: {task['run_at']}\n"
        f"Status: {status}\n"
        f"Repeat: {repeat}"
    )
    await query.message.reply_text(msg, reply_markup=build_scheduler_task_action_menu(task))


@route(prefix="scheduler:edit:")
async def _handle_scheduler_edit(query, task_id):
    if task_id.startswith("_idx_"):
        await render_menu(query, "⚠️ Task not found. Please refresh the task list.", build_scheduler_menu())
        return
    user_id = query.from_user.id
    set_pending_action(user_id, "scheduler_edit", {"task_id": task_id})
    await render_menu(query, "📝 Send the updated task description:", InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Cancel", callback_data="menu:scheduler")]
    ]))


@route(exact="scheduler:search")
async def _handle_scheduler_search(query):
    user_id = query.from_user.id
    set_pending_action(user_id, "scheduler_search")
    await render_menu(query, "🔍 Enter a keyword to search tasks:", InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Cancel", callback_data="menu:scheduler")]
    ]))


async def _render_scheduler_search_page(query, page: int, keyword: str):
    from .scheduler import load_tasks
    all_tasks = load_tasks()
    kw = keyword.lower()
    filtered = [t for t in all_tasks if kw in t.get("prompt", "").lower() or kw in t.get("id", "").lower()]
    if not filtered:
        await render_menu(query, f"🔍 No results for \"{keyword}\"", build_scheduler_menu())
        return

    total = len(filtered)
    total_pages = (total + _TASK_PAGE_SIZE - 1) // _TASK_PAGE_SIZE
    page = max(1, min(page, total_pages))
    start = (page - 1) * _TASK_PAGE_SIZE
    page_tasks = filtered[start:start + _TASK_PAGE_SIZE]
    await render_menu(query, f"🔍 Results for \"{keyword}\"", build_scheduler_tasks_menu(page_tasks, "list", page, total_pages))


@route(prefix="scheduler:search:")
async def _handle_scheduler_search_page(query, page_str):
    try:
        page = int(page_str)
    except ValueError:
        page = 1
    keyword = get_search_query(query.from_user.id)
    if not keyword:
        await render_menu(query, "⚠️ Search expired, please try again.", build_scheduler_menu())
        return
    await _render_scheduler_search_page(query, page, keyword)


@route(prefix="scheduler:delete:")
async def _handle_scheduler_delete_id(query, task_id):
    from .scheduler import load_tasks, save_tasks
    tasks = load_tasks()
    tasks = [t for t in tasks if t.get("id") != task_id]
    save_tasks(tasks)
    await render_menu(query, "✅ Task deleted", build_scheduler_menu())


@authorized
async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🖥️ Main Menu", reply_markup=build_main_menu())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id != AUTHORIZED_USER_ID:
        await query.edit_message_text("❌ Unauthorized.")
        return

    data = query.data

    handler = EXACT_ROUTES.get(data)
    if handler:
        await handler(query)
        return

    for prefix, handler in PREFIX_ROUTES:
        if data.startswith(prefix):
            rest = data[len(prefix):]
            await handler(query, rest)
            return

    await query.answer("Unknown action")
