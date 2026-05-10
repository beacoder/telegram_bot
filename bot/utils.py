import os
import shutil
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from .config import (
    AGENT_MEDIA_DIR,
    AGENT_HOME,
    SESSION_MARKER,
    TELEGRAM_MAX_LENGTH,
    PROXY_URL,
    OPENCODE_TIMEOUT,
    MODELS,
    WHISPER_CPP_BIN,
    WHISPER_MODEL,
)


def get_model() -> str:
    from .state import get_model_key
    return MODELS[get_model_key()]


def clear_session():
    if os.path.exists(SESSION_MARKER):
        os.remove(SESSION_MARKER)


def sanitize_prompt(prompt: str) -> str:
    if not prompt:
        return ""
    prompt = prompt.strip()
    if len(prompt) > 10000:
        prompt = prompt[:10000]
    return prompt


def cleanup_media():
    for item in os.listdir(AGENT_MEDIA_DIR):
        item_path = os.path.join(AGENT_MEDIA_DIR, item)
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
        else:
            os.remove(item_path)


def validate_whisper():
    return all([
        WHISPER_CPP_BIN,
        WHISPER_MODEL,
        os.path.isfile(WHISPER_CPP_BIN),
        os.access(WHISPER_CPP_BIN, os.X_OK),
        os.path.isfile(WHISPER_MODEL),
    ])


async def run_process(cmd, timeout=300, cwd=None, env=None):
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return (proc.returncode, stdout.decode().strip(), stderr.decode().strip())
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return (None, stdout, "timeout")
