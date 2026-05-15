import os
import tempfile
import logging
from pathlib import Path
from .config import SESSION_MARKER, AGENT_HOME, OPENCODE_TIMEOUT, PROXY_URL
from .utils import get_model, run_process, cleanup_media


async def run_agent(prompt: str) -> str:
    has_marker = os.path.exists(SESSION_MARKER)
    session_id = Path(SESSION_MARKER).read_text().strip() if has_marker else ""
    model = get_model()

    cmd = ["opencode", "run", "--model", model, "--dangerously-skip-permissions"]
    if session_id:
        cmd.extend(["--session", session_id])
    elif has_marker:
        cmd.append("--continue")
    cmd.append(prompt)

    env = os.environ.copy()
    env["HTTP_PROXY"] = PROXY_URL
    env["HTTPS_PROXY"] = PROXY_URL

    rc, stdout, stderr = await run_process(
        cmd,
        timeout=OPENCODE_TIMEOUT,
        cwd=AGENT_HOME,
        env=env,
    )

    if rc is None:
        return "❌ Agent timed out."

    if rc != 0 and stderr:
        logging.error(f"opencode error (rc={rc}): {stderr}")
        return "❌ Agent failed with error."

    if not stdout:
        return "⚠️ Agent returned empty response."

    Path(SESSION_MARKER).touch()

    return stdout


async def execute_task(prompt: str, update=None, app=None, task_info: str = None):
    from .state import agent_lock, is_voice_enabled
    from .messaging import send_text, send_files, send_audio
    from .media import validate_piper, text_to_speech, filter_chinese_text

    if agent_lock.locked():
        await send_text("⚠️ Another task running, dropping this request.", update, app)
        return

    async with agent_lock:
        try:
            if task_info:
                await send_text(f"🚀 {task_info}", update, app)
            await send_text("🧠 Thinking...", update, app)
            response = await run_agent(prompt)

            use_tts = is_voice_enabled() and validate_piper()
            if use_tts:
                cn_text = filter_chinese_text(response)
                if cn_text.strip():
                    audio_path = tempfile.mktemp(suffix=".wav")
                    tts_result = await text_to_speech(cn_text, audio_path)
                    if tts_result and os.path.exists(tts_result):
                        await send_audio(tts_result, update, app)
                        os.remove(tts_result)

            await send_text(response, update, app)
            await send_files(update, app)
            await send_text("✅ Agent finished.", update, app)
        finally:
            cleanup_media()
