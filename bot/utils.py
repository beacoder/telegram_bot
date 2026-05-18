import os
import shutil
import shlex
import asyncio
from .config import (
    AGENT_MEDIA_DIR,
    SESSION_MARKER,
    PROXY_URL,
    MODELS,
    WHISPER_CPP_BIN,
    WHISPER_MODEL,
)


def get_model() -> str:
    from .state import get_model_key
    return MODELS[get_model_key()]


def new_session():
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


async def run_process(cmd, timeout=300, cwd=None, env=None, track_process=False):
    cmd_str = shlex.join(cmd) if isinstance(cmd, list) else cmd
    proc = await asyncio.create_subprocess_shell(
        cmd_str,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd
    )

    if track_process:
        from .state import set_running_process
        set_running_process(proc)

    stdout, stderr = b"", b""
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        returncode = proc.returncode
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        returncode = None
    finally:
        if track_process:
            from .state import clear_running_process
            clear_running_process()

    clean_out = (stdout or b"").decode(errors="replace").strip()
    clean_err = (stderr or b"").decode(errors="replace").strip()

    return (returncode, clean_out, clean_err)
