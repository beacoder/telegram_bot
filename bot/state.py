import asyncio
from .config import CURRENT_MODEL_KEY

current_model_key = CURRENT_MODEL_KEY
agent_lock = asyncio.Lock()
voice_enabled = False


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
