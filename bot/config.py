import os
import logging

AGENT_HOME = os.path.expanduser("~/agent")
AGENT_MEDIA_DIR = os.path.join(AGENT_HOME, "media")
AGENT_UPLOAD_DIR = os.path.join(AGENT_HOME, "upload")
AGENT_SCHEDULE_FILE = os.path.join(AGENT_HOME, "schedule.json")
SESSION_MARKER = os.path.join(AGENT_HOME, ".session_started")
OPENCODE_DB_PATH = os.path.expanduser("~/.local/share/opencode/opencode.db")

DEFAULT_MAX_FILE_SIZE = 50 * 1024 * 1024

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("AUTHORIZED_USER_ID"))
PROXY_URL = os.getenv("PROXY_URL")
WHISPER_CPP_DIR = os.path.expanduser(os.getenv("WHISPER_CPP_DIR", ""))
WHISPER_MODEL = os.path.expanduser(os.getenv("WHISPER_MODEL", ""))
WHISPER_CPP_BIN = os.path.join(WHISPER_CPP_DIR, "build/bin/whisper-cli")

PIPER_DIR = os.path.expanduser(os.getenv("PIPER_DIR", ""))
PIPER_MODEL = os.getenv("PIPER_MODEL", "")
PIPER_BIN = os.path.join(PIPER_DIR, "piper") if PIPER_DIR else "piper"

TELEGRAM_MAX_LENGTH = 4000
OPENCODE_TIMEOUT = 300
MAX_FILE_SIZE = DEFAULT_MAX_FILE_SIZE
LOG_LEVEL = "INFO"

MODELS = {
    "free": "opencode/minimax-m2.5-free",
    "flash": "deepseek/deepseek-v4-flash",
    "pro": "deepseek/deepseek-v4-pro",
}
CURRENT_MODEL_KEY = "free"

os.makedirs(AGENT_HOME, exist_ok=True)
os.makedirs(AGENT_MEDIA_DIR, exist_ok=True)
os.makedirs(AGENT_UPLOAD_DIR, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("./telegram_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
