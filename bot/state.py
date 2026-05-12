import asyncio
from datetime import datetime
from .config import CURRENT_MODEL_KEY

current_model_key = CURRENT_MODEL_KEY
agent_lock = asyncio.Lock()
voice_enabled = False
bot_start_time: datetime = None
scheduler_error: str = None


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
