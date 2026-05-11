import asyncio
import os
import tempfile
from telegram import Update
from telegram.ext import ContextTypes
from .config import TELEGRAM_MAX_LENGTH, AUTHORIZED_USER_ID, MAX_FILE_SIZE, MODELS
from .utils import sanitize_prompt, new_session
from .media import extract_file_info, download_file, maybe_transcribe
from .agent import execute_task
from .state import set_model_key, toggle_voice, is_voice_enabled, get_model_key
from .media import text_to_speech, validate_piper


async def send_text(text: str, update: Update = None, app=None):
    if not text or not text.strip():
        return
    chunks = [
        text[i:i + TELEGRAM_MAX_LENGTH]
        for i in range(0, len(text), TELEGRAM_MAX_LENGTH)
    ]
    for chunk in chunks:
        if update:
            await update.message.reply_text(chunk)
        elif app:
            await app.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=chunk)
        await asyncio.sleep(0.6)


async def send_audio(audio_path: str, update: Update = None, app=None):
    if not os.path.exists(audio_path):
        return
    try:
        with open(audio_path, "rb") as f:
            if update:
                await update.message.reply_voice(voice=f)
            elif app:
                await app.bot.send_voice(chat_id=AUTHORIZED_USER_ID, voice=f)
    except Exception as e:
        await send_text(f"Failed to send audio: {e}", update, app)


async def send_files(update: Update = None, app=None):
    from .config import AGENT_MEDIA_DIR
    if not os.path.exists(AGENT_MEDIA_DIR):
        return
    files = sorted(
        [os.path.join(AGENT_MEDIA_DIR, f) for f in os.listdir(AGENT_MEDIA_DIR)],
        key=os.path.getmtime
    )
    for path in files:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                if update:
                    await update.message.reply_document(document=f)
                elif app:
                    await app.bot.send_document(chat_id=AUTHORIZED_USER_ID, document=f)
        except Exception as e:
            await send_text(f"❌ Failed to send file: {path}", update, app)


async def handle_voice_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    enabled = toggle_voice()
    status = "enabled" if enabled else "disabled"
    await send_text(f"🔊 Voice output {status}.", update)


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    file_obj, file_name, is_voice = extract_file_info(update.message)

    if not file_obj:
        await send_text("⚠️ Unsupported file type.", update)
        return

    if (file_obj.file_size or 0) > MAX_FILE_SIZE:
        await send_text(f"⚠️ File too large. Max: {MAX_FILE_SIZE // (1024*1024)}MB", update)
        return

    try:
        file_path = await download_file(file_obj, file_name)
        await send_text(f"✅ File saved: {file_path}", update)

        transcript = await maybe_transcribe(file_path, is_voice, update, send_text)

        if transcript:
            await execute_task(transcript, update, None, "Running agent from transcript...")
    except Exception as e:
        await send_text(f"❌ Failed to download file: {e}", update)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    prompt = sanitize_prompt(update.message.text)
    if not prompt:
        await send_text("⚠️ Empty message.", update)
        return

    await execute_task(prompt, update, None)


async def handle_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("free")
    await send_text(f"✅ Switched to {MODELS['free']}", update)


async def handle_flash(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("flash")
    await send_text(f"✅ Switched to {MODELS['flash']}", update)


async def handle_pro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    set_model_key("pro")
    await send_text(f"✅ Switched to {MODELS['pro']}", update)


async def handle_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return
    new_session()
    await send_text("✅ Session cleared. Next message starts fresh.", update)


async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != AUTHORIZED_USER_ID:
        await send_text("❌ Unauthorized.", update)
        return

    await send_text(
        "Available commands:\n"
        "/help - Show this help\n"
        "/clear - Clear session\n"
        "/free - Use free model\n"
        "/flash - Use deepseek-v4-flash model\n"
        "/pro - Use deepseek-v4-pro model\n"
        "/voice - Toggle voice output (TTS)\n"
        "Any other message - Run agent\n",
        update
    )
