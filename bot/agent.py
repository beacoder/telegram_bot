import os
import asyncio
import logging
from pathlib import Path
from .config import SESSION_MARKER, AGENT_HOME, PROXY_URL, OPENCODE_TIMEOUT
from .utils import get_model, run_process, cleanup_media


async def run_agent(prompt: str) -> str:
    use_continue = os.path.exists(SESSION_MARKER)
    model = get_model()

    cmd = ["opencode", "run", "--model", model, "--dangerously-skip-permissions"]
    if use_continue:
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

    Path(SESSION_MARKER).touch()

    if rc != 0 and stderr:
        logging.error(f"opencode error (rc={rc}): {stderr}")

    if not stdout:
        return "⚠️ Agent returned empty response."

    return stdout


async def execute_task(prompt: str, update=None, app=None, task_info: str = None):
    from .state import agent_lock

    if agent_lock.locked():
        from .handlers import send_text
        await send_text("⚠️ Another task running, dropping this request.", update, app)
        return

    from .handlers import send_text, send_files

    async with agent_lock:
        try:
            if task_info:
                await send_text(f"🚀 {task_info}", update, app)
            await send_text("🧠 Thinking...", update, app)
            response = await run_agent(prompt)
            await send_text(response, update, app)
            await send_files(update, app)
            await send_text("✅ Agent finished.", update, app)
        finally:
            cleanup_media()
