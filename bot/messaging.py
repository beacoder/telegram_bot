import asyncio
import os
from .config import TELEGRAM_MAX_LENGTH, AUTHORIZED_USER_ID, AGENT_MEDIA_DIR


async def send_text(text: str, update=None, app=None, reply_markup=None):
    if not text or not text.strip():
        return
    chunks = [
        text[i:i + TELEGRAM_MAX_LENGTH]
        for i in range(0, len(text), TELEGRAM_MAX_LENGTH)
    ]
    for i, chunk in enumerate(chunks):
        kw = {}
        if reply_markup and i == len(chunks) - 1:
            kw["reply_markup"] = reply_markup
        if update:
            await update.message.reply_text(chunk, **kw)
        elif app:
            await app.bot.send_message(chat_id=AUTHORIZED_USER_ID, text=chunk, **kw)
        await asyncio.sleep(0.6)


async def send_audio(audio_path: str, update=None, app=None):
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


async def send_files(update=None, app=None):
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
        except Exception:
            await send_text(f"❌ Failed to send file: {path}", update, app)
