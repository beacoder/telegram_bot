import os
import json
import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from calendar import monthrange
from .config import AGENT_SCHEDULE_FILE
from .agent import execute_task


def load_tasks() -> list:
    if not os.path.exists(AGENT_SCHEDULE_FILE):
        return []
    try:
        with open(AGENT_SCHEDULE_FILE, "r") as f:
            content = f.read().strip()
            if content:
                tasks = json.loads(content)
                changed = False
                for task in tasks:
                    if not task.get("id"):
                        task["id"] = str(uuid.uuid4())[:8]
                        changed = True
                if changed:
                    save_tasks(tasks)
                return tasks
            return []
    except Exception as e:
        logging.exception(f"[schedule] load failed: {e}")
        return []


def save_tasks(tasks: list):
    tmp_file = AGENT_SCHEDULE_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(tasks, f, indent=2)
    os.replace(tmp_file, AGENT_SCHEDULE_FILE)


def is_task_due(task: dict) -> bool:
    if task.get("done"):
        return False
    try:
        run_at = datetime.strptime(task["run_at"], "%Y-%m-%d %H:%M")
    except (ValueError, KeyError):
        return False
    return (datetime.now() >= run_at)


def compute_next_run(task: dict):
    try:
        repeat = task.get("repeat")
        if not repeat:
            return None
        current_run = datetime.strptime(task["run_at"], "%Y-%m-%d %H:%M")

        if repeat == "daily":
            next_run = current_run + timedelta(days=1)
        elif repeat.startswith("weekly:"):
            weekday = int(repeat.split(":")[1])
            if not 1 <= weekday <= 7:
                return None
            next_run = current_run + timedelta(days=1)
            while next_run.isoweekday() != weekday:
                next_run += timedelta(days=1)
        elif repeat.startswith("monthly:"):
            day = int(repeat.split(":")[1])
            if not 1 <= day <= 31:
                return None
            year, month = current_run.year, current_run.month
            if current_run.day < day:
                max_day = monthrange(year, month)[1]
                next_day = min(day, max_day)
                next_run = current_run.replace(day=next_day)
            else:
                month += 1
                if month > 12:
                    month = 1
                    year += 1
                max_day = monthrange(year, month)[1]
                next_day = min(day, max_day)
                next_run = current_run.replace(year=year, month=month, day=next_day)
        elif repeat.startswith("interval:"):
            val = repeat.split(":")[1]
            if val.endswith("m"):
                minutes = int(val[:-1])
                next_run = current_run + timedelta(minutes=minutes)
            elif val.endswith("h"):
                hours = int(val[:-1])
                next_run = current_run + timedelta(hours=hours)
            else:
                next_run = None
        else:
            next_run = None

        if next_run:
            return next_run.strftime("%Y-%m-%d %H:%M")
        return None

    except Exception as e:
        logging.exception(f"[schedule] compute failed: {e}")
        return None


async def run_scheduled_tasks(app):
    tasks = load_tasks()
    updated = []

    for task in tasks:
        try:
            if is_task_due(task):
                await execute_task(task["prompt"], None, app, f"Running: {task['prompt']}")
                next_run = compute_next_run(task)
                if next_run:
                    task["run_at"] = next_run
                    task["done"] = False
                else:
                    task["done"] = True
        except Exception as e:
            logging.exception(f"[schedule] task failed: {task}")
        updated.append(task)

    if updated:
        save_tasks(updated)


async def scheduler_loop(app):
    from .state import clear_scheduler_error, set_scheduler_error
    from .messaging import send_text
    while True:
        try:
            clear_scheduler_error()
            await run_scheduled_tasks(app)
        except Exception as e:
            try:
                set_scheduler_error(str(e))
                await send_text(f"❌ Tasks error: {e}", None, app)
            except Exception:
                logging.exception("Failed to send Telegram alert")
        await asyncio.sleep(30)
