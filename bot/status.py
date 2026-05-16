import shutil
import psutil
from datetime import datetime
from pathlib import Path
from .config import MODELS, AGENT_HOME
from .state import get_model_key, get_bot_start_time, get_scheduler_status


async def build_status_text() -> str:
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

    return (
        f"📊 Bot Status\n"
        f"─────────────\n"
        f"Uptime:    {uptime}\n"
        f"Model:     {model}\n"
        f"Tasks: {scheduler}\n"
        f"CPU:       {cpu_pct}%\n"
        f"Memory:    {mem_info}\n"
        f"Disk:      {disk_info}"
    )
