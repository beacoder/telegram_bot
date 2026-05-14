import asyncio
from datetime import datetime
from .config import CURRENT_MODEL_KEY

current_model_key = CURRENT_MODEL_KEY
agent_lock = asyncio.Lock()
voice_enabled = False
bot_start_time: datetime = None
scheduler_error: str = None
user_pending_action: dict = {}
_search_query: dict = {}


def set_search_query(user_id: int, query: str):
    _search_query[user_id] = query


def get_search_query(user_id: int) -> str:
    return _search_query.get(user_id, "")


def clear_search_query(user_id: int):
    _search_query.pop(user_id, None)


def get_model_key():
    return current_model_key


def set_model_key(key: str):
    global current_model_key
    current_model_key = key


def toggle_voice():
    global voice_enabled
    voice_enabled = not voice_enabled
    return voice_enabled


def is_voice_enabled():
    return voice_enabled


def set_bot_start_time(dt: datetime):
    global bot_start_time
    bot_start_time = dt


def get_bot_start_time() -> datetime:
    return bot_start_time


def set_scheduler_error(msg: str):
    global scheduler_error
    scheduler_error = msg


def clear_scheduler_error():
    global scheduler_error
    scheduler_error = None


def get_scheduler_status() -> str:
    if scheduler_error is None:
        return "Running"
    return f"Stopped: {scheduler_error}"


def set_pending_action(user_id: int, action: str, data: dict = None):
    user_pending_action[user_id] = {"action": action, "data": data or {}}


def get_pending_action(user_id: int) -> dict:
    return user_pending_action.get(user_id)


def clear_pending_action(user_id: int):
    user_pending_action.pop(user_id, None)
