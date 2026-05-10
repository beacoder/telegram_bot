import os
from datetime import datetime
from telegram import Update
from .config import AGENT_UPLOAD_DIR
from .utils import run_process, validate_whisper


def extract_file_info(message):
    if message.document:
        return message.document, message.document.file_name or f"document_{datetime.now().timestamp()}", False
    if message.photo:
        return message.photo[-1], f"photo_{datetime.now().timestamp()}", False
    if message.video:
        file_name = getattr(message.video, "file_name", None)
        return message.video, file_name or f"video_{datetime.now().timestamp()}", False
    if message.audio:
        file_name = getattr(message.video, "file_name", None)
        return message.audio, file_name or f"audio_{datetime.now().timestamp()}", False
    if message.voice:
        return message.voice, f"voice_{datetime.now().timestamp()}.ogg", True
    return None, None, False


async def download_file(file_obj, file_name: str) -> str:
    file = await file_obj.get_file()
    safe_name = os.path.basename(file_name)
    dest_path = os.path.join(AGENT_UPLOAD_DIR, safe_name)
    await file.download_to_drive(dest_path)
    return dest_path


async def convert_to_wav(input_path: str) -> str:
    output_path = input_path.rsplit(".", 1)[0] + ".wav"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ar", "16000",
        "-ac", "1",
        output_path
    ]

    rc, _, stderr = await run_process(cmd, timeout=60)

    if rc != 0:
        logging.error(f"ffmpeg failed: {stderr}")
        return None

    os.remove(input_path)
    return output_path


async def transcribe_voice(file_path: str):
    from .config import WHISPER_CPP_BIN, WHISPER_MODEL, WHISPER_CPP_DIR
    import logging

    cmd = [
        WHISPER_CPP_BIN,
        "-m", WHISPER_MODEL,
        "-f", file_path,
        "--no-timestamps",
        "--no-prints",
    ]

    rc, stdout, stderr = await run_process(
        cmd,
        timeout=300,
        cwd=WHISPER_CPP_DIR,
    )

    if rc != 0:
        logging.error(f"whisper.cpp transcription failed error (rc={rc}): {stderr}")
        return ""

    transcript = stdout.strip()
    if not transcript:
        return ""

    return transcript


async def maybe_transcribe(file_path: str, is_voice: bool, update: Update, send_text_func):
    if not is_voice:
        return None

    if not validate_whisper():
        return None

    await send_text_func("🎙 Transcribing...", update)

    if file_path.endswith(".ogg"):
        file_path = await convert_to_wav(file_path)

    if file_path:
        transcript = await transcribe_voice(file_path)

    if not transcript:
        return None

    os.remove(file_path)
    await send_text_func(f"📝 Transcript:\n{transcript[:3000]}", update)
    return transcript
