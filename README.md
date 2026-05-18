# Telegram ↔ OpenCode Agent Bridge

## Overview

A Telegram bot that connects directly to an OpenCode agent backend. Supports persistent AI sessions, file uploads, interactive menus, multiple model switching, task scheduling, voice I/O, and proxy environments.

## Architecture

```
Telegram → Python Bot → OpenCode Agent
                          ↓
                    Local Workspace
                          ↓
                 Files + Agent Output
                          ↓
                   Telegram Response
```

## Project Structure

```
telegram_bot/
├── telegram_bot.py         # Bot entry point, Telegram app setup
├── README.md
├── bot/
│   ├── __init__.py
│   ├── agent.py            # OpenCode agent runner + task executor
│   ├── auth.py             # @authorized decorator for command handlers
│   ├── config.py           # Configuration, env vars, constants
│   ├── handlers.py         # Command handlers (help, status, history, etc.)
│   ├── media.py            # File download, voice transcription, Piper TTS
│   ├── menu.py             # Interactive menu system (builders + callback handler)
│   ├── messaging.py        # Telegram message utilities (send_text, send_audio, send_files)
│   ├── scheduler.py        # Task scheduler (cron-like)
│   ├── state.py            # Agent lock, running process, model key, bot start time, pending actions
│   ├── status.py           # Bot health status builder (uptime, CPU, memory, disk)
│   └── utils.py            # Helpers (process runner, cleanup, health check)
```

## Interactive Menu

Use `/menu` or the menu appears automatically on bot startup:

| Menu | Options |
|------|---------|
| **🧠 Models** | Free / Flash / Pro (with ✓ on current) |
| **📂 Sessions** | New Session / View History (with pagination) / Search Session |
| **📅 Tasks** | New Task / View Tasks / Search Task |
| **🎤 Voice** | Toggle voice output ON/OFF |
| **📊 Status** | Uptime, model, tasks health, CPU, memory, disk |

To add a task, just send a natural language prompt like:
*"提醒我每天早上7点起床"*, *"remind me to check email tomorrow at 9am"*, *"每天下午3点查询大盘数据"*

All menus have ⬅️ Back buttons to return to the main menu.

## Commands

| Command | Description |
|---------|-------------|
| `/menu` | Show interactive menu |
| `/help` | Show available commands |
| `/status` | Show bot health info (uptime, model, tasks, CPU, memory, disk) |
| `/history [n]` | Show session history (latest n, default all) |
| `/continue <session-id>` | Continue session |
| `/delete <session-id>` | Delete a session |
| `/free` | Switch to the free model (`opencode/minimax-m2.5-free`) |
| `/flash` | Switch to `deepseek/deepseek-v4-flash` model |
| `/pro` | Switch to `deepseek/deepseek-v4-pro` model |
| `/voice` | Toggle voice output (TTS) |
| `/cancel` | Stop the currently running agent task |
| `/new` | New session |
| `/restart` | Restart bot (auto-reconnects on health check failure) |
| Any text | Send to the agent for processing |
| Any file | Download and optionally transcribe, then run agent |

## Key Features

- **Interactive Menu System** — Button-driven menus for all bot functions; no need to memorize slash commands
- **Remote AI Agent Access** — Use Telegram as a mobile interface for your OpenCode agent
- **Persistent Sessions** — Maintains conversation continuity across messages; continue any past session by title
- **File Support** — Documents, images, videos, audio; files auto-returned to Telegram
- **Voice Transcription** — Voice messages transcribed via whisper.cpp before agent execution
- **Multiple AI Models** — Switch between `free`, `flash`, and `pro` models
- **Task Scheduler** — Lightweight cron-style scheduler supporting daily, weekly, monthly, and interval-based tasks; add/edit/delete tasks via menu; add tasks using natural language
- **Bot Status Monitoring** — Real-time bot health: uptime, model, scheduler health, CPU, memory, disk usage
- **Voice Output (TTS)** — Agent responses converted to speech via Piper; non-Chinese characters filtered automatically for stable Chinese voice synthesis
- **Proxy Support** — Works through HTTP/SOCKS proxy environments
- **Task Locking** — Prevents overlapping agent executions
- **Cancel Running Task** — Use `/cancel` or menu button to stop an in-progress agent task mid-execution
- **Automatic Health Check & Restart** — Background health check verifies Telegram API connectivity every 60s; auto-restarts on failure; manual restart via `/restart` command
- **Authorized User Only** — All operations restricted to `AUTHORIZED_USER_ID`

## Configuration

Set these environment variables before running:

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Your Telegram bot token from @BotFather |
| `AUTHORIZED_USER_ID` | Yes | Your Telegram user ID (integer) |
| `PROXY_URL` | No | HTTP/SOCKS proxy URL (e.g., `socks5://127.0.0.1:7890`) |
| `WHISPER_CPP_DIR` | No | Path to whisper.cpp directory for voice transcription |
| `WHISPER_MODEL` | No | Path to whisper.cpp model file |
| `PIPER_DIR` | No | Path to Piper TTS directory |
| `PIPER_MODEL` | No | Path to Piper model file (.onnx) |

Add [OpenCode Configuration](https://github.com/beacoder/llm/tree/main/opencode)

### schedule.json

Place in `~/agent/schedule.json`:

```json
[
  {
    "id": "a1b2c3d4",
    "prompt": "Give me today's tech news summary",
    "run_at": "2026-05-11 09:00",
    "repeat": "daily",
    "done": false
  },
  {
    "id": "e5f6g7h8",
    "prompt": "Weekly report",
    "run_at": "2026-05-17 10:00",
    "repeat": "weekly:1",
    "done": false
  },
  {
    "id": "i9j0k1l2",
    "prompt": "Monthly reminder",
    "run_at": "2026-06-01 08:00",
    "repeat": "monthly:1",
    "done": false
  },
  {
    "id": "m3n4o5p6",
    "prompt": "Ping check",
    "run_at": "2026-05-10 12:00",
    "repeat": "interval:30m",
    "done": false
  }
]
```

Repeat modes: `daily`, `weekly:N` (1=Mon), `monthly:N` (day), `interval:30m` / `interval:2h`

## Requirements

- Python 3
- [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot)
- [psutil](https://github.com/giampaolo/psutil) — for bot status monitoring
- [OpenCode CLI](https://opencode.ai)
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp) + model (optional, for voice transcription)
- [ffmpeg](https://github.com/ffmpeg/ffmpeg) (optional, for audio conversion)
- [Piper](https://github.com/OHF-Voice/piper1-gpl) + model (optional, for voice output TTS)

## Installation

```bash
pip install python-telegram-bot aiohttp psutil
git clone https://github.com/beacoder/telegram_bot.git
cd telegram_bot
# Set environment variables, then:
python telegram_bot.py
```

## Typical Workflow

1. Send a message, file, or use the interactive `/menu`
2. Bot downloads & transcribes if needed, forwards to OpenCode
3. Agent processes the request locally
4. Response text (with optional TTS voice) + generated files are returned to Telegram

## Security Notes

- Single-user design — `AUTHORIZED_USER_ID` restricts access
- Never expose your bot token publicly
- Run in trusted environments only

## License

MIT
