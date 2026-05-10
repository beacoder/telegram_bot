import os
import asyncio
import logging
from .config import PIPER_BIN, PIPER_MODEL


def validate_piper():
    if not PIPER_BIN or not PIPER_MODEL:
        return False
    return os.path.isfile(PIPER_BIN) and os.access(PIPER_BIN, os.X_OK) and os.path.isfile(PIPER_MODEL)


async def text_to_speech(text: str, output_path: str) -> str:
    cmd = [
        PIPER_BIN,
        "-m", PIPER_MODEL,
        "-f", "0",
        "--input-file", "-",
        "--output-file", output_path,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=text.encode()),
            timeout=120,
        )
        rc = proc.returncode
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logging.error("Piper TTS timed out")
        return ""

    if rc != 0:
        logging.error(f"Piper TTS failed (rc={rc}): {stderr.decode().strip()}")
        return ""

    if not os.path.exists(output_path):
        logging.error(f"Piper did not produce output file: {output_path}")
        return ""

    return output_path
