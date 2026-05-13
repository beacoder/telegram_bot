import os
import logging
import tempfile
from datetime import datetime
from telegram import Update
from .config import AGENT_UPLOAD_DIR, PIPER_BIN, PIPER_MODEL
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


async def convert_to_ogg(input_path: str) -> str:
    output_path = input_path.rsplit(".", 1)[0] + "_telegram.ogg"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-ar", "24000",
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


def validate_piper():
    if not PIPER_BIN or not PIPER_MODEL:
        return False
    return os.path.isfile(PIPER_BIN) and os.access(PIPER_BIN, os.X_OK) and os.path.isfile(PIPER_MODEL)


def filter_chinese_text(text: str) -> str:
    return "".join(
        c for c in text
        if "\u4e00" <= c <= "\u9fff"
        or "\u3000" <= c <= "\u303f"
        or "\uff00" <= c <= "\uffef"
        or "a" <= c <= "z"
        or "A" <= c <= "Z"
        or "0" <= c <= "9"
        or c in " .,:;!?。，：；！？、"
    )


async def text_to_speech(text: str, output_path: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
        tmp_path = tmp.name

    try:
        cmd = [
            PIPER_BIN,
            "-m", PIPER_MODEL,
            "--input-file", tmp_path,
            "--output-file", output_path,
        ]

        rc, _, stderr = await run_process(cmd, timeout=120)

        if rc != 0:
            logging.error(f"Piper TTS failed (rc={rc}): {stderr}")
            return ""

        if not os.path.exists(output_path):
            logging.error(f"Piper did not produce output file: {output_path}")
            return ""

        ogg_path = await convert_to_ogg(output_path)
        if not ogg_path:
            return ""

        return ogg_path
    finally:
        os.remove(tmp_path)
